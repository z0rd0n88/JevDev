"""Build the findings corpus for Finding Triage from a repo's merged PRs.

Sources, per PR: review reports posted as PR comments, review reports saved under docs/reviews in the
checkout, and review or finding-fixer output found in Claude transcripts that name the PR. Raw text is
cached under .local/raw (gitignored); the corpus is one JSON row per (pr, round, finding).

    python3 corpus_findings.py --limit 15                 # the 15 latest merged PRs
    python3 corpus_findings.py --pr 1110                  # one PR (tracer bullet)
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from finding_triage import parse_fixer_report, parse_report, redact

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local"
RAW = LOCAL / "raw"
REPORT_HEAD = re.compile(r"^#{1,3} (Multi-Agent Review|vista-dw-review|dw-review|Review sweep|Open-PR sweep)\b", re.M)
FIXER_LINE = re.compile(r"^[A-Z]+-?\d+\s{2,}(?:fix-here|real-but-decided-elsewhere|refuted)\s{2,}", re.M)
SHAPED = re.compile(r"^(?:- \*\*|#{2,4} )(?:CRITICAL|HIGH|MEDIUM|LOW)\b", re.M)  # finding bullets without a report header
ATTR_LINE = re.compile(r"^\s*- \*{0,2}(?:Where|Failure path)\*{0,2}:", re.M)  # what separates a finding from a changelog bullet


def report_shaped(text: str) -> bool:
    return bool(REPORT_HEAD.search(text)) or len(FIXER_LINE.findall(text)) >= 2 or (len(SHAPED.findall(text)) >= 3 and bool(ATTR_LINE.search(text)))
REVIEWED_SHA = re.compile(r"(?:reviewed at|Reviewed HEAD \||fix commit|at) `([0-9a-f]{7,40})`")
TRANSCRIPT_GLOB = os.path.expanduser("~/.claude/projects/*{slug}*/*.jsonl")
CODEX_GLOB = os.path.expanduser("~/.codex/sessions/**/*.jsonl")
REVIEW_DIRS = ("docs/reviews", ".claude/reviews")  # where the review skills save their records


def sh(*args: str) -> str:
    return subprocess.run(list(args), capture_output=True, text=True, errors="replace", check=True).stdout


def cached(path: Path, produce) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redact(produce()))
    return path.read_text()


def merged_prs(slug: str, limit: int, only: list[int]) -> list[dict]:
    fields = "number,title,mergedAt,headRefOid,headRefName,mergeCommit,commits"
    if only:
        return [json.loads(cached(RAW / f"pr-{n}.json", lambda n=n: sh("gh", "pr", "view", str(n), "--repo", slug, "--json", fields))) for n in only]
    text = cached(RAW / f"prs-merged-{limit}.json", lambda: sh("gh", "pr", "list", "--repo", slug, "--state", "merged", "--limit", str(limit), "--json", fields))
    return json.loads(text)


def pr_comments(slug: str, n: int) -> list[dict]:
    """Issue comments, review bodies and review-thread comments, oldest first."""
    out = []
    for kind, route in (("issue", f"issues/{n}/comments"), ("review", f"pulls/{n}/reviews"), ("thread", f"pulls/{n}/comments")):
        text = cached(RAW / f"pr-{n}-{kind}.json", lambda route=route: sh("gh", "api", "--paginate", f"repos/{slug}/{route}"))
        for c in json.loads(text):
            if c.get("body"):
                out.append({"kind": kind, "author": c["user"]["login"], "ts": c.get("created_at") or c.get("submitted_at"), "body": c["body"]})
    return sorted(out, key=lambda c: c["ts"] or "")


def docs_reviews(checkout: Path, n: int) -> list[dict]:
    out = []
    pat = re.compile(rf"(?:#|pull/|PR )#?{n}\b")
    for p in sorted(p for d in REVIEW_DIRS for p in glob.glob(str(checkout / d / "*.md"))):
        text = Path(p).read_text(errors="replace")
        if not pat.search(text):
            continue
        section = re.search(rf"^## #{n}:.*?(?=^## #\d+:|\Z)", text, re.S | re.M)
        if section is None and re.search(r"^## #\d+:", text, re.M):
            continue  # a per-PR record that only mentions this PR in passing
        body = section.group(0) if section else text
        if section and "Findings" in body:
            body = "# dw-review sweep section\n" + body
        ts = datetime.fromtimestamp(int(sh("git", "-C", str(checkout), "log", "-1", "--format=%ct", "--", p) or 0), timezone.utc).isoformat()
        out.append({"kind": "docs", "author": "repo", "ts": ts, "body": body, "ref": os.path.relpath(p, checkout)})
    return out


def transcript_files(slug: str) -> list[str]:
    """Claude transcripts for the project, plus Codex rollouts whose first lines name it."""
    name = slug.split("/")[-1]
    files = sorted(glob.glob(TRANSCRIPT_GLOB.format(slug=name)))
    for f in sorted(glob.glob(CODEX_GLOB, recursive=True)):
        try:
            with open(f, errors="replace") as fh:
                if name in fh.read(20000):
                    files.append(f)
        except OSError:
            pass
    return files


def transcript_reports(slug: str, prs: list[int]) -> dict[int, list[dict]]:
    """Report-shaped text blocks and finding-fixer report lines that name a PR, per PR, from transcripts.

    One pass over every file; a block counts when it names the PR and looks like a review report, a
    reviewer hand-back, or a finding-fixer report. Blocks are cached under .local/raw.
    """
    mention = {n: re.compile(rf"(?:#|pull/|pr/|PR )#?{n}\b") for n in prs}
    out: dict[int, list[dict]] = {n: [] for n in prs}
    seen: set[int] = set()
    for f in transcript_files(slug):
        sess = os.path.basename(f).replace("rollout-", "codex-")[:14 if "codex" in f else 8]
        with open(f, errors="replace") as fh:
            for i, line in enumerate(fh):
                if line.startswith('{"type":"api-request'):  # byte-identical copies of user/assistant lines
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o.get("message"), dict) and o["message"].get("role") == "system":
                    continue
                for t in strings(o):
                    if len(t) < 400 or hash(t) in seen or not report_shaped(t):
                        continue
                    for n, pat in mention.items():
                        if pat.search(t[:600]):  # a report names its target up top; a passing mention deeper down is another target
                            seen.add(hash(t))
                            ref = f"transcript-{sess}-{i}"
                            cached(RAW / f"{ref}.md", lambda t=t: t)
                            out[n].append({"kind": "transcript", "author": sess, "ts": o.get("timestamp") or "", "body": t, "ref": ref})
    return out


def strings(value, depth: int = 0) -> list[str]:
    """Every string anywhere in a transcript line: message blocks, queued hand-backs, attachments, tool inputs."""
    if isinstance(value, str):
        return [value]
    if depth > 8:
        return []
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v, depth + 1)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v, depth + 1)]
    return []


def _verdicts(r: dict) -> int:
    return sum(1 for f in r["findings"] if f.get("verdict") in ("DEMOTED", "REFUTED") or f.get("skeptic"))


def tool_of(body: str) -> str | None:
    head = body.lstrip()[:200]
    for key, tool in (("Multi-Agent Review", "multi-agent-review"), ("vista-dw-review", "vista-dw-review"), ("dw-review", "dw-review"), ("Review sweep", "sweep"), ("Open-PR sweep", "sweep")):
        if key in head:
            return tool
    if len(FIXER_LINE.findall(body)) >= 2:
        return "finding-fixer"
    return "reviewer-output" if report_shaped(body) else None


def build(pr: dict, sources: list[dict]) -> dict:
    """Order the PR's reports into rounds, join finding-fixer rulings, and mark next-round restatements."""
    reports, fixers = [], []
    for s in sources:
        tool = tool_of(s["body"])
        if tool is None:
            continue
        if tool == "finding-fixer":
            fixers.append({**s, "rulings": parse_fixer_report(s["body"])})
            continue
        findings = parse_report(s["body"])
        sha = REVIEWED_SHA.search(s["body"])
        reports.append({**s, "tool": tool, "sha": sha.group(1) if sha else pr["headRefOid"], "findings": findings})
    reports.sort(key=lambda r: r["ts"] or "")
    rounds = []
    for r in reports:  # a PR comment that repeats a saved or transcript report is the same round
        if not r["findings"] and re.search(r"\*\*(CRITICAL|HIGH|MEDIUM|LOW)\*\*|^#+ (CRITICAL|HIGH|MEDIUM|LOW)", r["body"], re.M):
            print(f"PARSE FAILURE: PR {pr['number']} {r['kind']}:{r.get('ref', r['author'])} has severity markers but 0 findings parsed", file=sys.stderr)
        titles = {f["title"] for f in r["findings"]}
        dup = next((x for x in rounds if (titles and len(titles & {f["title"] for f in x["findings"]}) / len(titles) > 0.8)
                    or (not titles and not x["findings"] and x["tool"] == r["tool"])), None)
        if dup:
            dup["also"].append(f"{r['kind']}:{r.get('ref', r['author'])}")
            if _verdicts(r) > _verdicts(dup):  # keep the copy that carries the skeptic's verdicts
                dup.update({k: r[k] for k in ("findings", "tool", "sha", "body")})
        else:
            rounds.append({**r, "also": []})
    rows = []
    for k, r in enumerate(rounds):
        prior = rounds[k - 1]["findings"] if k else []
        nxt = rounds[k + 1]["findings"] if k + 1 < len(rounds) else None
        for f in r["findings"]:
            num = int(re.sub(r"\D", "", f["id"]) or 0)
            ruling = next((fx["rulings"][f["id"]] for fx in fixers if f["id"] in fx["rulings"] and (fx["ts"] or "") >= (r["ts"] or "")), None)
            restated = None
            if nxt is not None:
                restated = any(num in g["prior_refs"] or difflib.SequenceMatcher(None, f["title"], g["title"]).ratio() >= 0.6 for g in nxt)
            rows.append({
                "pr": pr["number"],
                "round": k + 1,
                "tool": r["tool"],
                "source": f"{r['kind']}:{r.get('ref', r['author'])}",
                "also": r["also"],
                "ts": r["ts"],
                "reviewed_sha": r["sha"],
                "head_sha": pr["headRefOid"],
                "pr_commits": [c["oid"] for c in pr.get("commits", [])],
                "merged_at": pr["mergedAt"],
                **f,
                "prior_round": [{"id": p["id"], "severity": p["severity"], "title": p["title"], "where": p["where"]} for p in prior],
                "fixer": ruling,
                "restated_next_round": restated,
            })
    return {"pr": pr["number"], "title": pr["title"], "rounds": len(rounds), "fixer_reports": len(fixers), "rows": rows, "sources": [f"{s['kind']}:{s.get('ref', s['author'])}" for s in sources]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-slug", default="VistaMarkets/VistaMobileBE")
    ap.add_argument("--checkout", default=os.path.expanduser("~/VistaMobileBE"))
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--pr", type=int, action="append", default=[])
    ap.add_argument("--out", default=str(LOCAL / "findings-corpus.jsonl"))
    ap.add_argument("--no-transcripts", action="store_true")
    a = ap.parse_args()
    prs = merged_prs(a.repo_slug, a.limit, a.pr)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = with_verdict = 0
    from_transcripts = {} if a.no_transcripts else transcript_reports(a.repo_slug, [p["number"] for p in prs])
    with out.open("w") as fh:
        for pr in prs:
            n = pr["number"]
            sources = pr_comments(a.repo_slug, n) + docs_reviews(Path(a.checkout), n) + from_transcripts.get(n, [])
            b = build(pr, sources)
            for row in b["rows"]:
                fh.write(json.dumps(row) + "\n")
            verdicts = sum(1 for r in b["rows"] if r["verdict"] in ("DEMOTED", "REFUTED") or r["skeptic"] or r["fixer"])
            total += len(b["rows"])
            with_verdict += verdicts
            tools = sorted({r["tool"] for r in b["rows"]})
            print(f"PR {n:>5}  rounds={b['rounds']}  findings={len(b['rows']):>3}  with_verdict={verdicts:>3}  fixer_reports={b['fixer_reports']}  tools={','.join(tools) or '-'}  "
                  f"{'NO TOOL REVIEW FOUND  ' if not b['rows'] else ''}sources={len(b['sources'])}  {pr['title'][:50]}")
    print(f"\n{total} findings, {with_verdict} with a skeptic or finding-fixer verdict, {total - with_verdict} orphaned -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
