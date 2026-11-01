"""Finding Triage and Convergence, phase 1 (offline).

Parse review reports into findings, build the per-finding state (text, cited hunk, blame age,
prior-round findings), ask Jev the triage questions through jev_patterns.call, and decide whether a
review->fix->re-review loop has converged. Nothing here is wired into a review skill yet.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jev_patterns import call

# ponytail: provisional thresholds, all in one place; tune from calibrate_findings.py output.
DUPLICATE_AT = 0.85  # duplicate_of_prior_round at or above -> "duplicate"
PRE_EXISTING_AT = 0.85  # 1 - introduced_by_this_diff at or above -> "pre-existing"
MECHANICAL_AT = 0.85  # fix_is_mechanical at or above -> skip the reviewer round for it
SAME_ROUND_AT = 0.85  # round_materially_same_as_previous at or above, plus zero new HIGH -> converged
SEVERITY = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]  # score index order
NOTE_AT_OR_BELOW = "MEDIUM"  # pre-existing findings at or below this go to "noted, not blocking"
HUNK_CONTEXT = 15

FINDING_QUESTIONS = {
    "introduced_by_this_diff": {
        "type": "noul",
        "instructions": "Did the change under review introduce the defect in `finding`, or did it already exist before? Use `blame` (how old the cited lines are and whether this change wrote them) and `hunk`.",
        "criteria": {
            "true": "The cited lines were written or changed by this change, or the defect only became reachable because of it",
            "false": "The cited lines predate this change and the same defect was already there on the base branch",
        },
    },
    "duplicate_of_prior_round": {
        "type": "noul",
        "instructions": "Does `finding` restate one of the `prior_round` findings (the same defect, at the same or additional sites, however reworded), rather than report a new defect?",
        "criteria": {
            "true": "Same defect as a prior-round finding, at the same or additional sites with the same cause, possibly rephrased or with a new severity",
            "false": "A defect no prior-round finding describes: a different defect at the same place, a defect the prior fix created, or a missing test for the prior fix",
        },
    },
    "severity": {
        "type": "score",
        "instructions": "Rate `finding` on the code-review rubric.",
        "criteria": [
            "LOW: style or minor suggestion, optional",
            "MEDIUM: maintainability concern, consider fixing",
            "HIGH: bug or significant quality issue, fix before merge",
            "CRITICAL: security vulnerability or data-loss risk, block merge",
        ],
    },
    "fix_is_mechanical": {
        "type": "noul",
        "instructions": "Can the `fix` in `finding` be applied without a design decision: one obvious edit a careful engineer would make the same way?",
        "criteria": {
            "true": "Rename, add a null check, add the missing assertion, log a field, update a comment or spec line",
            "false": "Needs a decision about behaviour, a spec amendment, a new test design, or touches more than the cited lines",
        },
    },
}

ROUND_QUESTIONS = {
    "round_materially_same_as_previous": {
        "type": "noul",
        "instructions": "Compare `round` with `prior_round`. Is the new round materially the same set of defects, so another fix-and-review pass would find nothing new?",
        "criteria": {
            "true": "Every finding in `round` restates or narrows a prior finding; nothing new of HIGH or CRITICAL severity",
            "false": "At least one finding in `round` reports a defect the prior round did not, or a prior fix created a new one",
        },
    },
}


def keystone_question(findings: list[dict]) -> dict:
    return {
        "keystone": {
            "type": "choice",
            "instructions": "Fixing which one of these findings makes the most of the others moot or easier?",
            "criteria": {f["id"]: f"{f.get('severity', '?')}: {f['title']}" for f in findings},
        }
    }


# --- parsing -----------------------------------------------------------------

SEV = r"(CRITICAL|HIGH|MEDIUM|LOW)"
VERDICT = r"(CONFIRMED|DEMOTED|REFUTED|SUPPORTED)"
# `- **LOW** (reviewer said MEDIUM) — title  [DEMOTED]`  (sweep / dw-review bullets)
BULLET = re.compile(rf"^- \*\*{SEV}\*\*(?: \(reviewer said {SEV}\))?\s*(?:[—–-]\s*)?(.*?)\s*(?:\[{VERDICT}\])?\s*$")
# `### HIGH **MUST FIX**: title` / `### MEDIUM: title`  (saved dw-review reports)
HEADING = re.compile(rf"^#{{2,4}} {SEV}(?: \*\*MUST FIX\*\*)?: (.*)$")
# `## High Findings` bucket, then `### NUM-1 — title` or `### R3-01 — title [HIGH]`  (Multi-Agent Review reports)
BUCKET = re.compile(rf"^#{{2,3}} (Critical|High|Medium|Low) Findings\b", re.I)
IDHEAD = re.compile(rf"^#{{3,4}} ([A-Z]+\d*-?\d+) [—–-] (.*?)(?: \[{SEV}\])?\s*$")
# `| L1 | finding | fix |`  (vista-dw-review table) and `| F3 | HIGH | title | ... |`
TABLE = re.compile(r"^\| *([A-Z]+-?\d+) *\| *(.*?) *\|(.*)$")
# `| MEDIUM | **CRYPTO-1 — title** | location | reviewer | description |`  (Multi-Agent Review medium/low table)
SEVTABLE = re.compile(rf"^\| *{SEV} *\| *\*\*([A-Z]+\d*-?\d+)(?: / [A-Z]+-?\d+)* [—–-] (.*?)\*\* *\| *(.*?) *\| *(.*?) *\| *(.*?) *\|?\s*$")
# `- ~~title~~ — reason`  (refuted bullets)
STRUCK = re.compile(r"^- ~~(.*?)~~\s*[—–-]?\s*(.*)$")
# `- **F2's claim that ...** (lane): reason`  (refuted bullets in saved dw-review reports)
BOLD = re.compile(r"^- \*\*(.+?)\*\*\s*(?:\([^)]*\))?:?\s*(.*)$")
# `F1  fix-here  applied  summary`  (finding-fixer report lines)
FIXER = re.compile(r"^([A-Z]+-?\d+)\s{2,}(fix-here|real-but-decided-elsewhere|refuted|skipped|open)\s{2,}(applied|no edit|skipped|open)\s+(.*)$")
ATTR = re.compile(r"^\s*- \*{0,2}(Where|Location|Failure path|Description|Fix|Suggested fix|Evidence|Skeptic(?: confirmed by)?)\*{0,2}:\*{0,2}\s*(.*)$")
ATTR_KEY = {"where": "where", "location": "where", "failure": "failure", "description": "failure", "fix": "fix", "suggested": "fix", "evidence": "evidence", "skeptic": "skeptic"}
WHERE = re.compile(r"([\w./-]+\.\w{1,6}):(\d+)(?:[-–—](\d+))?")  # reports use ASCII and en/em dashes for ranges
PRIOR_REF = re.compile(r"\bFindings? (\d+(?:(?:,| and) \d+)*)")
# Known key shapes (prefixed tokens, AWS, Google, JWT, PEM blocks) and generic `key=value` / `user:pass@` forms.
# Every value class stops at quotes, backslashes, commas, semicolons and whitespace so redacting serialized JSON keeps it parseable.
# `sk`, `hf` and `npm` also start ordinary names (`sk-learn`, `hf_hub_download`, `npm_package_version`), so those need the key's own shape.
TOKEN = re.compile(
    r"(?:(?:(?<![A-Za-z0-9_])|(?<=\\[nrt]))(?:(?:ghp|gho|ghu|ghs|github_pat|xox[a-z]|vck|glpat|rpa)[-_][A-Za-z0-9_-]{8,}"
    r"|sk[-_](?=[A-Za-z_-]*\d)[A-Za-z0-9_-]{20,}|(?:hf|npm)_[A-Za-z0-9]{30,})"
    r"|AKIA[A-Z0-9]{12,}|AIza[0-9A-Za-z_-]{20,}"
    r"|Bearer [A-Za-z0-9._-]{12,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]*)?"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----)",
    re.S,
)
# A keyword as a whole identifier part: `tokenizer` and `secretary` are out, `accessToken` and `DISCORD_BOT_TOKEN` are in.
_SECRET_KEY = r"[A-Za-z0-9_-]{0,40}(?:api[_-]?key|secret|token|password|passwd)s?(?:(?:[_-]|(?-i:[A-Z]))[A-Za-z0-9_-]{0,40})?"
# Values that name something instead of holding it, with nothing else up to where the value ends: `A_CONSTANT`, a closed call or
# index (`getenv(name)`, `headers["x"]`), a dotted reference.
# ponytail: a digit-free underscored all-caps secret passes as a constant; none seen in the corpus.
_END = r"\.?[)\]}]*(?:[\\\"'`,;\s]|$)"
_NOT_SECRET = rf"(?:[A-Z]+(?:_[A-Z]+)+|[A-Za-z_][A-Za-z_.]*[(\[][^\s)\]]*[)\]]|[a-z]+(?:\.[A-Za-z]+)+){_END}"
ASSIGNED = re.compile(rf"(?i)({_SECRET_KEY})(\\*[\"'`]?\s*[=:]\s*\\*[\"'`]?)(?!(?-i:{_NOT_SECRET}))[^\\\"'`,;\s]{{12,}}")
SECRET_KEY = re.compile(_SECRET_KEY, re.I)
NOT_SECRET = re.compile(_NOT_SECRET)
# `host:8080/path/@me` is a port and a path; a raw `/` in a real password still counts.
USERINFO = re.compile(r"(://)[^/\s:@\"']+:(?!\d+(?:[/?#]|$))[^\\@\s\"']+@")


def redact(text: str) -> str:
    text = TOKEN.sub("[REDACTED]", text)
    text = ASSIGNED.sub(r"\1\2[REDACTED]", text)
    return USERINFO.sub(r"\1[REDACTED]@", text)


def redact_json(value, key: str = ""):
    """A decoded JSON value: strings by content, and whole when their key names a secret, since no `key=` is left to match."""
    if isinstance(value, str):
        if value and SECRET_KEY.fullmatch(key) and not NOT_SECRET.fullmatch(value):
            return "[REDACTED]"
        return redact(value)
    if isinstance(value, list):
        return [redact_json(v, key) for v in value]
    if isinstance(value, dict):
        return {redact(k): redact_json(v, k) for k, v in value.items()}
    return value


def section_verdict(heading: str) -> str | None:
    h = heading.lower()
    if "refuted" in h or "demoted" in h:
        return "REFUTED"
    if "survived" in h or "confirmed" in h:
        return "CONFIRMED"
    return None


def parse_report(text: str, prefix: str = "F") -> list[dict]:
    """Findings in a review report, in order. Each has id, severity, title, verdict, where, failure, fix, skeptic."""
    findings: list[dict] = []
    current: dict | None = None
    verdict_ctx: str | None = None
    table_sev: str | None = None
    bucket_sev: str | None = None
    for raw in redact(text).splitlines():
        line = raw.rstrip()
        m = IDHEAD.match(line)
        if m and (bucket_sev or m.group(3)):
            fid, title, sev = m.groups()
            current = _new(findings, prefix, sev or bucket_sev, title, verdict_ctx or "CONFIRMED", fid)
            continue
        if line.startswith("#") and not HEADING.match(line):
            verdict_ctx = section_verdict(line)
            m = BUCKET.match(line)
            bucket_sev = m.group(1).upper() if m else (bucket_sev if line.startswith("###") else None)
            m = re.search(rf"\(.*?\b{SEV}\b", line)
            table_sev = m.group(1) if m and "finding" in line.lower() else None
            current = None
            continue
        m = BOLD.match(line)
        if m and verdict_ctx == "REFUTED" and not BULLET.match(line):
            current = _new(findings, prefix, None, m.group(1), "REFUTED")
            current["skeptic"] = m.group(2)
            continue
        m = BULLET.match(line)
        if m:
            sev, said, title, verdict = m.groups()
            current = _new(findings, prefix, sev, title, verdict or verdict_ctx)
            if said:
                current["reviewer_said"] = said
                current["verdict"] = current["verdict"] or "DEMOTED"
            continue
        m = HEADING.match(line)
        if m:
            sev, title = m.groups()
            current = _new(findings, prefix, sev, title.replace("**MUST FIX**: ", ""), verdict_ctx or "CONFIRMED")
            current["must_fix"] = "MUST FIX" in line
            continue
        m = STRUCK.match(line)
        if m:
            current = _new(findings, prefix, None, m.group(1), "REFUTED")
            current["skeptic"] = m.group(2)
            continue
        m = SEVTABLE.match(line)
        if m:
            sev, fid, title, where, _reviewer, desc = m.groups()
            current = _new(findings, prefix, sev, title, verdict_ctx or "CONFIRMED", fid)
            current["where"] = where
            current["locations"] = [(p, int(a), int(b or a)) for p, a, b in WHERE.findall(where)]
            current["failure"] = desc
            continue
        m = TABLE.match(line)
        if m and table_sev and not m.group(1).startswith("-"):
            fid, title, rest = m.groups()
            current = _new(findings, prefix, table_sev, title, verdict_ctx or "CONFIRMED", fid)
            current["fix"] = rest.strip(" |")
            continue
        m = ATTR.match(line)
        if m and current is not None:
            key = ATTR_KEY[m.group(1).lower().split()[0]]
            current[key] = m.group(2)
            if key == "where":
                current["locations"] = [(p, int(a), int(b or a)) for p, a, b in WHERE.findall(m.group(2))]
            continue
        if current is not None and line.startswith("  ") and current.get("failure") is None and not line.lstrip().startswith("-"):
            current["body"] = (current.get("body", "") + " " + line.strip()).strip()
    for f in findings:
        f["prior_refs"] = sorted({int(n) for grp in PRIOR_REF.findall(f["title"]) for n in re.findall(r"\d+", grp)})
    return findings


def _new(findings, prefix, sev, title, verdict, fid=None) -> dict:
    f = {
        "id": fid or f"{prefix}{len(findings) + 1}",
        "severity": sev,
        "title": title.strip(),
        "verdict": verdict,
        "where": None,
        "locations": [],
        "failure": None,
        "fix": None,
        "skeptic": None,
    }
    findings.append(f)
    return f


def parse_fixer_report(text: str) -> dict[str, dict]:
    """finding-fixer Step 5 lines, keyed by the reviewer's finding id."""
    out = {}
    for line in text.splitlines():
        m = FIXER.match(line.strip())
        if m:
            fid, ruling, action, note = m.groups()
            out[fid] = {"ruling": ruling, "action": action, "note": note.strip()}
    return out


# --- state builders (git) ------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace", check=False).stdout


def resolve_path(repo: Path, sha: str, path: str) -> str | None:
    """A report may cite a bare file name; find it in the tree at `sha`. None when it is absent or ambiguous."""
    if "/" in path:
        return path
    hits = [p for p in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines() if p == path or p.endswith("/" + path)]
    return hits[0] if len(hits) == 1 else None


def hunk(repo: Path, sha: str, path: str, start: int, end: int, context: int = HUNK_CONTEXT) -> str:
    text = git(repo, "show", f"{sha}:{path}")
    if not text:
        return ""
    lines = text.splitlines()
    lo, hi = max(1, start - context), min(len(lines), end + context)
    return "\n".join(f"{n}: {lines[n - 1]}" for n in range(lo, hi + 1))


def blame(repo: Path, sha: str, path: str, start: int, end: int, pr_commits: set[str], at: datetime) -> dict:
    """Median age in days of the cited lines at `sha`, and the share of them written inside the PR."""
    out = git(repo, "blame", "--line-porcelain", "-L", f"{start},{end}", sha, "--", path)
    ages, inside, total = [], 0, 0
    commit = None
    for line in out.splitlines():
        if re.match(r"^[0-9a-f]{40} \d+ \d+", line):
            commit = line[:40]
            total += 1
            inside += commit in pr_commits
        elif line.startswith("committer-time ") and commit:
            ages.append((at - datetime.fromtimestamp(int(line.split()[1]), timezone.utc)).days)
    ages.sort()
    return {
        "lines": total,
        "median_age_days": ages[len(ages) // 2] if ages else None,
        "written_in_this_change": round(inside / total, 2) if total else None,
    }


def finding_state(f: dict, prior: list[dict], repo: Path | None, sha: str | None, pr_commits: set[str], at: datetime) -> dict:
    state = {
        "id": f["id"],
        "finding": {k: f.get(k) for k in ("severity", "title", "where", "failure", "fix", "body")},
        "prior_round": [{"id": p["id"], "severity": p.get("severity"), "title": p["title"], "where": p.get("where")} for p in prior],
        "hunk": "",
        "blame": None,
        "state_error": None,
    }
    if not f.get("locations"):
        state["state_error"] = "no location cited"
        return state
    if not (repo and sha):
        state["state_error"] = "no checkout or commit to read"
        return state
    cited, start, end = f["locations"][0]
    path = resolve_path(repo, sha, cited)
    if path is None:
        state["state_error"] = f"{cited} is absent or ambiguous at {sha[:8]}"
        return state
    state["hunk"] = redact(hunk(repo, sha, path, start, end))  # checkout text goes to Jev
    b = blame(repo, sha, path, start, end, pr_commits, at)
    if not state["hunk"] or not b["lines"]:
        state["state_error"] = f"{path}:{start}-{end} unreadable at {sha[:8]}"
        state["hunk"] = ""
        return state
    state["blame"] = b
    return state


# --- grading -------------------------------------------------------------------


def label(answers: dict, has_blame: bool = True) -> dict:
    """Labels from one finding's answers. Without blame evidence a finding is never called pre-existing."""
    intro = answers["introduced_by_this_diff"]["noul"]
    sev = SEVERITY[min(int(round(answers["severity"]["score"])), len(SEVERITY) - 1)]
    pre_existing = has_blame and 1 - intro >= PRE_EXISTING_AT
    return {
        "introduced_p": intro,
        "duplicate_p": answers["duplicate_of_prior_round"]["noul"],
        "mechanical_p": answers["fix_is_mechanical"]["noul"],
        "severity_score": answers["severity"]["score"],
        "severity_jev": sev,
        "duplicate": answers["duplicate_of_prior_round"]["noul"] >= DUPLICATE_AT,
        "pre_existing": pre_existing,
        "mechanical": answers["fix_is_mechanical"]["noul"] >= MECHANICAL_AT,
        "noted_not_blocking": pre_existing and SEVERITY.index(sev) <= SEVERITY.index(NOTE_AT_OR_BELOW),
    }


def grade_round(findings: list[dict], prior: list[dict], *, repo=None, sha=None, pr_commits=frozenset(), at=None, model=None, job="finding-triage") -> dict:
    """One Jev call per finding, one for the round, one for the keystone. Returns labels, convergence, and call stats."""
    at = at or datetime.now(timezone.utc)
    graded, calls, usd, tokens = [], 0, 0.0, 0
    for f in findings:
        state = finding_state(f, prior, repo, sha, set(pr_commits), at)
        r = call(state, FINDING_QUESTIONS, job=job, model=model)
        calls, usd, tokens = calls + 1, usd + _usd(r), tokens + _tokens(r)
        graded.append({**f, **label(r["answers"], state["blame"] is not None), "blame": state["blame"], "state_error": state["state_error"], "state_chars": len(str(state))})
    round_state = {
        "round": [{"id": g["id"], "severity": g["severity"], "title": g["title"], "where": g.get("where")} for g in graded],
        "prior_round": [{"id": p["id"], "severity": p.get("severity"), "title": p["title"], "where": p.get("where")} for p in prior],
    }
    same = None
    if prior:
        r = call(round_state, ROUND_QUESTIONS, job=job, model=model)
        calls, usd, tokens = calls + 1, usd + _usd(r), tokens + _tokens(r)
        same = r["answers"]["round_materially_same_as_previous"]["noul"]
    keystone = None
    if len(graded) > 1:
        r = call(round_state, keystone_question(graded), job=job, model=model)
        calls, usd, tokens = calls + 1, usd + _usd(r), tokens + _tokens(r)
        keystone = r["answers"]["keystone"]["choice"]
    return {
        "findings": graded,
        "same_as_previous_p": same,
        "keystone": keystone,
        "converged": converged(same, graded),
        "calls": calls,
        "estimated_usd": round(usd, 4),
        "input_tokens": tokens,
    }


def converged(same_p: float | None, graded: list[dict]) -> bool:
    """Loop stops when the round is materially the previous one and no new (non-duplicate, unrefuted) finding is HIGH or worse."""
    if same_p is None or same_p < SAME_ROUND_AT:
        return False
    return not any(new_high(g) for g in graded)


def new_high(g: dict) -> bool:
    """A graded finding that would keep the loop open: not a duplicate, not refuted by the skeptic, HIGH or worse per Jev."""
    return not g["duplicate"] and g.get("verdict") != "REFUTED" and SEVERITY.index(g["severity_jev"]) >= SEVERITY.index("HIGH")


def _usd(r: dict) -> float:
    from jev_patterns import estimated_usd

    return estimated_usd(r)


def _tokens(r: dict) -> int:
    from jev_patterns import input_tokens

    return input_tokens(r)
