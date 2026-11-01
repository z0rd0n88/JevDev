"""Replay the findings corpus through finding_triage and report how Jev's labels agree with the record.

    bash with_jev_key.sh python3 calibrate_findings.py               # all rows in .local/findings-corpus.jsonl
    bash with_jev_key.sh python3 calibrate_findings.py --pr 1110     # one PR
    python3 calibrate_findings.py --from-graded                       # re-cut the report, no Jev calls

Truth:
  duplicate   = hand label from tests/fixtures/findings/labels-pr<N>-r<K>.json when the row has one (same defect as a
                prior-round finding, at the same or additional sites, the Jev question's own definition); else the
                proxy: title matches a prior-round title at ratio >= 0.6. follow_on (new defect about a prior subject)
                is a separate label and is never counted as duplicate.
  introduced  = blame: at least half the cited lines were written inside the PR. Rows with no readable blame are
                excluded and counted. The skeptic's "pre-existing pattern" notes are reported on their own line.
Every number is printed as counted; nothing is rounded away.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import finding_triage as ft

ROOT = Path(__file__).resolve().parent
LABELS_GLOB = str(ROOT / "tests/fixtures/findings/labels-pr*-r*.json")
DEFAULT_OUT = str(ROOT / ".local/calibration.jsonl")
PRE_EXISTING_WORDS = re.compile(r"already exists on main|pre-?existing|same shape already|not new|predates|repeat of an existing|existing pattern", re.I)
INTRODUCED_AT = 1 - ft.PRE_EXISTING_AT  # a finding is called introduced unless Jev is this sure it is not


def load_labels() -> dict[tuple[int, int], dict]:
    out = {}
    for p in sorted(glob.glob(LABELS_GLOB)):
        d = json.loads(Path(p).read_text())
        out[(d["pr"], d["round"])] = d["rows"]
    return out


def label_of(g: dict, labels: dict) -> dict | None:
    return labels.get((g["pr"], g["round"]), {}).get(g["id"])


def proxy_duplicate(g: dict) -> bool:
    return any(difflib.SequenceMatcher(None, g["title"], p["title"]).ratio() >= 0.6 for p in g["prior_round"])


def truth_duplicate(g: dict, labels: dict) -> bool:
    lab = label_of(g, labels)
    return lab["duplicate"] if lab else proxy_duplicate(g)


def truth_introduced(g: dict) -> bool | None:
    b = g.get("blame")
    if b and b.get("written_in_this_change") is not None:
        return b["written_in_this_change"] >= 0.5
    return None


def prf(pairs: list[tuple[bool, bool]]) -> str:
    tp = sum(1 for p, t in pairs if p and t)
    fp = sum(1 for p, t in pairs if p and not t)
    fn = sum(1 for p, t in pairs if not p and t)
    tn = sum(1 for p, t in pairs if not p and not t)
    prec = f"{tp / (tp + fp):.2f}" if tp + fp else "n/a"
    rec = f"{tp / (tp + fn):.2f}" if tp + fn else "n/a"
    return f"n={len(pairs)} tp={tp} fp={fp} fn={fn} tn={tn} precision={prec} recall={rec}"


def live_out(out: str, prs: list[int]) -> Path:
    """A --pr run on the default path writes beside it, so the full file --from-graded reads is never replaced by a subset."""
    if prs and out == DEFAULT_OUT:
        return Path(out).with_name(f"calibration-pr{'-'.join(map(str, prs))}.jsonl")
    return Path(out)


def grade(rows: list[dict], checkout: Path, model: str | None, out: Path) -> tuple[list[dict], int, float, int]:
    rounds: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in rows:
        rounds[(r["pr"], r["round"])].append(r)
    graded_rows: list[dict] = []
    calls, usd, tokens = 0, 0.0, 0
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")  # replaces `out` only once every round is graded; a failed run leaves its paid answers here
    with tmp.open("w") as fh:
        for (pr, k), fs in sorted(rounds.items()):
            at = datetime.fromisoformat(fs[0]["merged_at"].replace("Z", "+00:00"))
            res = ft.grade_round(fs, fs[0]["prior_round"], repo=checkout, sha=fs[0]["reviewed_sha"], pr_commits=set(fs[0]["pr_commits"]), at=at, model=model)
            calls, usd, tokens = calls + res["calls"], usd + res["estimated_usd"], tokens + res["input_tokens"]
            for g in res["findings"]:
                g["round_same_p"], g["round_converged"], g["round_keystone"] = res["same_as_previous_p"], res["converged"], res["keystone"]
                graded_rows.append(g)
                fh.write(json.dumps(g) + "\n")
            fh.flush()
            print(f"PR {pr} round {k}: {len(fs)} findings, same_as_previous={res['same_as_previous_p']}, converged={res['converged']}, keystone={res['keystone']}, calls={res['calls']}, est ${res['estimated_usd']:.4f}", file=sys.stderr)
    os.replace(tmp, out)
    return graded_rows, calls, usd, tokens


def report(graded_rows: list[dict], labels: dict, calls: int, usd: float, tokens: int, source: str) -> None:
    by_round: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for g in graded_rows:
        by_round[(g["pr"], g["round"])].append(g)
    per_round = [{"pr": pr, "round": k, "n": len(gs), "same_p": gs[0]["round_same_p"], "converged": gs[0]["round_converged"], "keystone": gs[0]["round_keystone"],
                  "new_high": sum(1 for g in gs if ft.new_high(g)), "tool": gs[0]["tool"]} for (pr, k), gs in sorted(by_round.items())]

    print("## Calibration\n")
    print(f"Rows: {len(graded_rows)} findings in {len(per_round)} rounds across {len({g['pr'] for g in graded_rows})} PRs. {source}\n")
    dup_rows = [g for g in graded_rows if g["prior_round"]]
    labelled = [g for g in dup_rows if label_of(g, labels)]
    print(f"- duplicate_of_prior_round at {ft.DUPLICATE_AT} (rows with a prior round; {len(labelled)} of {len(dup_rows)} hand-labelled, the rest by title proxy): {prf([(g['duplicate'], truth_duplicate(g, labels)) for g in dup_rows])}")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        print(f"  - at {t}: {prf([(g['duplicate_p'] >= t, truth_duplicate(g, labels)) for g in dup_rows])}")
    if labelled:
        print(f"  - title proxy vs hand label on the labelled rows: {prf([(proxy_duplicate(g), label_of(g, labels)['duplicate']) for g in labelled])}")
        follow = [g for g in labelled if label_of(g, labels)["follow_on"]]
        dups = [g for g in labelled if label_of(g, labels)["duplicate"]]
        rest = [g for g in labelled if g not in follow and g not in dups]
        for name, gs in (("duplicate", dups), ("follow_on", follow), ("neither", rest)):
            if gs:
                print(f"  - mean duplicate_p on hand-labelled {name} rows: {sum(g['duplicate_p'] for g in gs) / len(gs):.2f} (n={len(gs)}, min {min(g['duplicate_p'] for g in gs):.2f}, max {max(g['duplicate_p'] for g in gs):.2f})")
    print("  - duplicate_p per row (truth in brackets: D duplicate, F follow-on, - neither): " + ", ".join(
        f"{g['id']}={g['duplicate_p']:.2f}[{'D' if truth_duplicate(g, labels) else 'F' if (label_of(g, labels) or {}).get('follow_on') else '-'}]" for g in dup_rows))

    intro = [(g["introduced_p"] > INTRODUCED_AT, t) for g in graded_rows if (t := truth_introduced(g)) is not None]
    excluded = Counter(g["state_error"] or "blame empty" for g in graded_rows if truth_introduced(g) is None)
    print(f"- introduced_by_this_diff at p > {INTRODUCED_AT:.2f} (truth = blame, rows with readable blame only): {prf(intro)}")
    print(f"  - always-introduced baseline on the same rows: {prf([(True, t) for _, t in intro])}")
    for t in (0.3, 0.5, 0.7):
        print(f"  - at p > {t}: {prf([(g['introduced_p'] > t, tr) for g in graded_rows if (tr := truth_introduced(g)) is not None])}")
    print(f"  - excluded {sum(excluded.values())} rows: " + "; ".join(f"{n} {why}" for why, n in sorted(excluded.items(), key=lambda x: -x[1])))
    skeptic_pairs = [(g["introduced_p"] > INTRODUCED_AT, False) for g in graded_rows if g.get("skeptic") and PRE_EXISTING_WORDS.search(g["skeptic"])]
    print(f"  - vs the skeptic's 'pre-existing pattern' notes alone (truth false): {prf(skeptic_pairs)}")

    stated = [(g["severity_jev"], s) for g in graded_rows if (s := _stated(g))]
    print(f"- severity agrees with the reviewer's stated severity: {sum(1 for p, s in stated if p == s)}/{len(stated)}; Jev higher: {sum(1 for p, s in stated if ft.SEVERITY.index(p) > ft.SEVERITY.index(s))}, lower: {sum(1 for p, s in stated if ft.SEVERITY.index(p) < ft.SEVERITY.index(s))}")
    scores = defaultdict(list)
    for g in graded_rows:
        if (s := _stated(g)) and g.get("severity_score") is not None:
            scores[s].append(g["severity_score"])
    print("  - raw severity score by stated level (0 LOW .. 3 CRITICAL): " + "; ".join(f"{lvl} n={len(v)} mean {sum(v) / len(v):.2f} min {min(v):.2f} max {max(v):.2f}" for lvl, v in sorted(scores.items(), key=lambda x: ft.SEVERITY.index(x[0]))))
    skeptic_sev = [(g["severity_jev"], g["severity"]) for g in graded_rows if g.get("reviewer_said") and g["severity"]]
    print(f"  - agrees with the skeptic's demoted severity: {sum(1 for p, s in skeptic_sev if p == s)}/{len(skeptic_sev)}")
    ref = [g for g in graded_rows if g["verdict"] == "REFUTED"]
    print(f"- REFUTED findings graded: {len(ref)}; of them labelled duplicate {sum(1 for g in ref if g['duplicate'])}, pre-existing {sum(1 for g in ref if g['pre_existing'])}, mechanical {sum(1 for g in ref if g['mechanical'])}; they never count as new HIGH")
    fixer = [g for g in graded_rows if g.get("fixer")]
    print(f"- rows with a finding-fixer ruling: {len(fixer)}; mechanical label vs ruling fix-here: {prf([(g['mechanical'], g['fixer']['ruling'] == 'fix-here') for g in fixer])}")
    print(f"- noted_not_blocking: {sum(1 for g in graded_rows if g['noted_not_blocking'])}, mechanical: {sum(1 for g in graded_rows if g['mechanical'])}, duplicate: {sum(1 for g in graded_rows if g['duplicate'])}, pre_existing: {sum(1 for g in graded_rows if g['pre_existing'])}")
    print(f"- Jev calls: {calls}, input tokens: {tokens}, estimated cost: ${usd:.4f}")

    print("\n## Convergence\n")
    by_pr = defaultdict(list)
    for p in per_round:
        by_pr[p["pr"]].append(p)
    early = 0
    for pr, ps in sorted(by_pr.items()):
        last = max(p["round"] for p in ps)
        first_conv = next((p["round"] for p in ps if p["converged"]), None)
        if first_conv is not None and first_conv < last:
            early += 1
        print(f"- PR {pr}: {last} round(s); " + "; ".join(f"r{p['round']} n={p['n']} new_high={p['new_high']} same_p={p['same_p']} converged={p['converged']} keystone={p['keystone']}" for p in ps) + (f"  -> would have stopped at round {first_conv}" if first_conv and first_conv < last else ""))
    multi = sum(1 for ps in by_pr.values() if len(ps) > 1)
    print(f"\nPRs with 2+ rounds: {multi}; would have stopped one round earlier under the provisional thresholds: {early}.")

    print("\n## Per tool\n")
    tools = defaultdict(list)
    for g in graded_rows:
        tools[g["tool"]].append(g)
    for t, gs in sorted(tools.items()):
        print(f"- {t}: {len(gs)} findings; duplicate {sum(1 for g in gs if g['duplicate'])}, pre_existing {sum(1 for g in gs if g['pre_existing'])}, mechanical {sum(1 for g in gs if g['mechanical'])}, mean introduced_p {sum(g['introduced_p'] for g in gs) / len(gs):.2f}, mean duplicate_p {sum(g['duplicate_p'] for g in gs) / len(gs):.2f}, no blame {sum(1 for g in gs if g.get('blame') is None)}")


def _stated(g: dict) -> str | None:
    return g.get("reviewer_said") or g.get("severity")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", default=str(ROOT / ".local/findings-corpus.jsonl"))
    ap.add_argument("--checkout", default=str(Path.home() / "VistaMobileBE"))
    ap.add_argument("--pr", type=int, action="append", default=[])
    ap.add_argument("--model")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--from-graded", action="store_true", help="re-cut the report from --out without calling Jev")
    a = ap.parse_args()
    labels = load_labels()
    if a.from_graded:
        graded_rows = [json.loads(line) for line in Path(a.out).read_text().splitlines()]
        if a.pr:
            graded_rows = [g for g in graded_rows if g["pr"] in a.pr]
        report(graded_rows, labels, 0, 0.0, 0, f"Re-cut from {a.out}; no Jev calls this run.")
        return 0
    rows = [json.loads(line) for line in Path(a.corpus).read_text().splitlines()]
    if a.pr:
        rows = [r for r in rows if r["pr"] in a.pr]
    out = live_out(a.out, a.pr)
    graded_rows, calls, usd, tokens = grade(rows, Path(a.checkout), a.model, out)
    report(graded_rows, labels, calls, usd, tokens, f"Live run; graded rows written to {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
