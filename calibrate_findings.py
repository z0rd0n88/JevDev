"""Replay the findings corpus through finding_triage and report how Jev's labels agree with the record.

    bash with_jev_key.sh python3 calibrate_findings.py               # all rows in .local/findings-corpus.jsonl
    bash with_jev_key.sh python3 calibrate_findings.py --pr 1110     # one PR
    python3 calibrate_findings.py --from-graded                       # re-cut the report, no Jev calls

Truth proxies (the corpus has no human labels):
  duplicate   = the finding names a prior-round finding number, or its title matches a prior-round title (ratio >= 0.6)
  introduced  = the skeptic's note says the defect predates the change -> false; else blame says >= half the cited lines were written in the PR
Every number is printed as counted; nothing is rounded away.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import finding_triage as ft

ROOT = Path(__file__).resolve().parent
PRE_EXISTING_WORDS = re.compile(r"already exists on main|pre-?existing|same shape already|not new|predates|repeat of an existing|existing pattern", re.I)


def truth_duplicate(row: dict) -> bool:
    if row["prior_refs"]:
        return True
    return any(difflib.SequenceMatcher(None, row["title"], p["title"]).ratio() >= 0.6 for p in row["prior_round"])


def truth_introduced(row: dict, graded: dict) -> bool | None:
    if row.get("skeptic") and PRE_EXISTING_WORDS.search(row["skeptic"]):
        return False
    b = graded.get("blame")
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", default=str(ROOT / ".local/findings-corpus.jsonl"))
    ap.add_argument("--checkout", default=str(Path.home() / "VistaMobileBE"))
    ap.add_argument("--pr", type=int, action="append", default=[])
    ap.add_argument("--model")
    ap.add_argument("--out", default=str(ROOT / ".local/calibration.jsonl"))
    ap.add_argument("--from-graded", action="store_true", help="re-cut the report from --out without calling Jev")
    a = ap.parse_args()
    if a.from_graded:
        graded_rows = [json.loads(line) for line in open(a.out)]
        if a.pr:
            graded_rows = [g for g in graded_rows if g["pr"] in a.pr]
        calls = usd = tokens = 0
    else:
        rows = [json.loads(line) for line in open(a.corpus)]
        if a.pr:
            rows = [r for r in rows if r["pr"] in a.pr]
        rounds: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for r in rows:
            rounds[(r["pr"], r["round"])].append(r)
        graded_rows = []
        calls = usd = tokens = 0
        for (pr, k), fs in sorted(rounds.items()):
            at = datetime.fromisoformat(fs[0]["merged_at"].replace("Z", "+00:00"))
            res = ft.grade_round(fs, fs[0]["prior_round"], repo=Path(a.checkout), sha=fs[0]["reviewed_sha"], pr_commits=set(fs[0]["pr_commits"]), at=at, model=a.model)
            calls, usd, tokens = calls + res["calls"], usd + res["estimated_usd"], tokens + res["input_tokens"]
            for g, row in zip(res["findings"], fs):
                state = ft.finding_state(row, row["prior_round"], Path(a.checkout), row["reviewed_sha"], set(row["pr_commits"]), at)
                g["blame"] = state["blame"]
                g["round_same_p"], g["round_converged"], g["round_keystone"] = res["same_as_previous_p"], res["converged"], res["keystone"]
                graded_rows.append(g)
            print(f"PR {pr} round {k}: {len(fs)} findings, same_as_previous={res['same_as_previous_p']}, converged={res['converged']}, keystone={res['keystone']}, calls={res['calls']}, est ${res['estimated_usd']:.4f}", file=sys.stderr)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w") as fh:
            for g in graded_rows:
                fh.write(json.dumps(g) + "\n")

    per_round = []
    for (pr, k), gs in sorted({(g["pr"], g["round"]): [x for x in graded_rows if (x["pr"], x["round"]) == (g["pr"], g["round"])] for g in graded_rows}.items()):
        per_round.append({"pr": pr, "round": k, "n": len(gs), "same_p": gs[0]["round_same_p"], "converged": gs[0]["round_converged"], "keystone": gs[0]["round_keystone"],
                          "new_high": sum(1 for g in gs if not g["duplicate"] and ft.SEVERITY.index(g["severity_jev"]) >= 2), "tool": gs[0]["tool"]})

    print("## Calibration\n")
    print(f"Rows: {len(graded_rows)} findings in {len(per_round)} rounds across {len({g['pr'] for g in graded_rows})} PRs. Jev calls: {calls}, input tokens: {tokens}, estimated cost: ${usd:.4f}.\n")
    dup_rows = [g for g in graded_rows if g["prior_round"]]
    dup_pairs = [(g["duplicate"], truth_duplicate(g)) for g in dup_rows]
    print(f"- duplicate_of_prior_round at {ft.DUPLICATE_AT} (rows with a prior round only): {prf(dup_pairs)}")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        print(f"  - at {t}: {prf([(g['duplicate_p'] >= t, truth_duplicate(g)) for g in dup_rows])}")
    print("  - duplicate_p per row (restated proxy in brackets): " + ", ".join(f"{g['id']}={g['duplicate_p']:.2f}[{'R' if truth_duplicate(g) else '-'}]" for g in dup_rows))
    intro_pairs = [(1 - g["introduced_p"] < ft.PRE_EXISTING_AT, t) for g in graded_rows if (t := truth_introduced(g, g)) is not None]
    print(f"- introduced_by_this_diff: {prf(intro_pairs)}")
    skeptic_pairs = [(1 - g["introduced_p"] < ft.PRE_EXISTING_AT, False) for g in graded_rows if g.get("skeptic") and PRE_EXISTING_WORDS.search(g["skeptic"])]
    print(f"- introduced_by_this_diff vs skeptic 'pre-existing' notes only: {prf(skeptic_pairs)}")
    stated = [(g["severity_jev"], s) for g in graded_rows if (s := _stated(g))]
    same = sum(1 for p, s in stated if p == s)
    print(f"- severity agrees with the reviewer's stated severity: {same}/{len(stated)}; Jev higher: {sum(1 for p, s in stated if ft.SEVERITY.index(p) > ft.SEVERITY.index(s))}, lower: {sum(1 for p, s in stated if ft.SEVERITY.index(p) < ft.SEVERITY.index(s))}")
    skeptic_sev = [(g["severity_jev"], g["severity"]) for g in graded_rows if g.get("reviewer_said") and g["severity"]]
    print(f"- severity agrees with the skeptic's demoted severity: {sum(1 for p, s in skeptic_sev if p == s)}/{len(skeptic_sev)}")
    ref = [g for g in graded_rows if g["verdict"] == "REFUTED"]
    print(f"- REFUTED findings graded: {len(ref)}; of them labelled duplicate {sum(1 for g in ref if g['duplicate'])}, pre-existing {sum(1 for g in ref if g['pre_existing'])}, mechanical {sum(1 for g in ref if g['mechanical'])}")
    fixer = [g for g in graded_rows if g.get("fixer")]
    print(f"- rows with a finding-fixer ruling: {len(fixer)}; mechanical label vs ruling fix-here: {prf([(g['mechanical'], g['fixer']['ruling'] == 'fix-here') for g in fixer])}")
    print(f"- noted_not_blocking: {sum(1 for g in graded_rows if g['noted_not_blocking'])}, mechanical: {sum(1 for g in graded_rows if g['mechanical'])}, duplicate: {sum(1 for g in graded_rows if g['duplicate'])}, pre_existing: {sum(1 for g in graded_rows if g['pre_existing'])}")
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
        print(f"- {t}: {len(gs)} findings; duplicate {sum(1 for g in gs if g['duplicate'])}, pre_existing {sum(1 for g in gs if g['pre_existing'])}, mechanical {sum(1 for g in gs if g['mechanical'])}, mean introduced_p {sum(g['introduced_p'] for g in gs) / len(gs):.2f}, mean duplicate_p {sum(g['duplicate_p'] for g in gs) / len(gs):.2f}")
    return 0


def _stated(g: dict) -> str | None:
    return g.get("reviewer_said") or g.get("severity")


if __name__ == "__main__":
    sys.exit(main())
