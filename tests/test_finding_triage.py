"""Offline checks for finding_triage: the report parser on three real (redacted) review texts, grading
labels on a five-finding fixture, and convergence on a two-round fixture. Uses a stub jev on JEV_BIN."""

import atexit
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIX = ROOT / "tests/fixtures/findings"
TMP = Path(tempfile.mkdtemp())
atexit.register(shutil.rmtree, TMP, True)

# JEV resolves at import, so JEV_BIN must point at the stub before the import below.
os.environ["JEV_BIN"] = str(TMP / "jev")
os.environ["TYPESAFE_API_KEY"] = "k"
sys.path.insert(0, str(ROOT))

import finding_triage as ft  # noqa: E402

# The stub answers per finding id from answers.json; round questions get the "round" entry.
STUB = """#!/usr/bin/env python3
import json, sys
from pathlib import Path
state = json.loads(sys.stdin.read())
qs = json.loads(sys.argv[sys.argv.index("-q") + 1])
table = json.loads((Path(__file__).parent / "answers.json").read_text())
key = state.get("id") or "round"
answers = {}
for qid, q in qs.items():
    if q["type"] == "choice":
        answers[qid] = {"type": "choice", "choice": table["keystone"], "confidence": 0.9}
    elif q["type"] == "score":
        answers[qid] = {"type": "score", "score": table[key][qid], "confidence": 0.9}
    else:
        answers[qid] = {"type": "noul", "noul": table[key][qid]}
print(json.dumps({"model": "stub", "answers": answers, "usage": {"input_tokens": 10}}))
"""
(TMP / "jev").write_text(STUB)
(TMP / "jev").chmod(0o755)


def answers(table: dict) -> None:
    (TMP / "answers.json").write_text(json.dumps(table))


def finding(fid: str, sev: str, title: str) -> dict:
    return {"id": fid, "severity": sev, "title": title, "where": "a.kt:1-2", "locations": [], "failure": None, "fix": "x", "skeptic": None, "prior_refs": []}


def test_parses_sweep_comment_with_demoted_and_refuted() -> None:
    fs = ft.parse_report((FIX / "pr1110-sweep-comment.md").read_text())
    assert [(f["id"], f["severity"], f["verdict"]) for f in fs] == [
        ("F1", "LOW", "DEMOTED"), ("F2", "LOW", "DEMOTED"), ("F3", "MEDIUM", "CONFIRMED"), ("F4", "LOW", "CONFIRMED"), ("F5", None, "REFUTED")], fs
    assert fs[0]["reviewer_said"] == "MEDIUM"
    assert fs[0]["locations"] == [("Merchant/src/main/kotlin/com/vista/merchant/withdrawal/WithdrawalService.kt", 1224, 1231)]
    assert fs[0]["skeptic"].startswith("Mechanism real") and fs[2]["fix"].startswith("Add log capture")
    assert fs[4]["skeptic"].startswith("Not a defect in the diff")


def test_parses_vista_dw_review_table() -> None:
    fs = ft.parse_report((FIX / "pr1063-vista-dw-review-comment.md").read_text())
    assert [(f["id"], f["severity"], f["verdict"]) for f in fs] == [("L1", "LOW", "CONFIRMED"), ("L2", "LOW", "CONFIRMED")], fs
    assert fs[1]["fix"].startswith("Names `perseus08`")


def test_parses_saved_dw_review_headings_and_prior_refs() -> None:
    fs = ft.parse_report((FIX / "pr1065-dw-review-saved.md").read_text())
    sev = [(f["id"], f["severity"], f["verdict"]) for f in fs]
    assert sev[:3] == [("F1", "HIGH", "CONFIRMED"), ("F2", "HIGH", "CONFIRMED"), ("F3", "MEDIUM", "CONFIRMED")], sev
    assert fs[0]["must_fix"] and not fs[1]["must_fix"]
    assert fs[3]["title"].startswith("Finding 1 (SOL decimals") and fs[3]["prior_refs"] == [1]
    refuted = [f for f in fs if f["verdict"] == "REFUTED"]
    assert len(refuted) == 4 and refuted[0]["title"].startswith("F2's claim"), refuted


def test_parses_multi_agent_review_buckets() -> None:
    text = "# Multi-Agent Review: PR #9\n\n## High Findings\n\n### NUM-1 — Sweep omits fee\n\n- **Location:** `a/B.kt:317–322`\n- **Description:** wrong\n- **Suggested fix:** add fee\n\n## Low Findings\n\n### R2-03 — Typo [LOW]\n\n- **Location:** `docs/x.md:4`\n"
    fs = ft.parse_report(text)
    assert [(f["id"], f["severity"], f["where"], f["fix"]) for f in fs] == [("NUM-1", "HIGH", "`a/B.kt:317–322`", "add fee"), ("R2-03", "LOW", "`docs/x.md:4`", None)], fs


def test_parses_finding_fixer_report_lines() -> None:
    text = "F1  fix-here                    applied   now rejects\nF3  refuted                     no edit   unreachable\nnot a line\n"
    assert ft.parse_fixer_report(text) == {"F1": {"ruling": "fix-here", "action": "applied", "note": "now rejects"}, "F3": {"ruling": "refuted", "action": "no edit", "note": "unreachable"}}


def test_redacts_tokens() -> None:
    assert ft.redact("x ghp_abcdefghijklmnop y Bearer abcdefghijklmnop.q") == "x [REDACTED] y [REDACTED]"


def test_grades_five_findings_two_duplicates_one_pre_existing() -> None:
    prior = [finding("P1", "HIGH", "reject() loses the audit row"), finding("P2", "LOW", "typo in spec")]
    fs = [finding(f"F{i}", s, t) for i, (s, t) in enumerate([
        ("HIGH", "reject() still loses the audit row"), ("LOW", "spec typo remains"), ("MEDIUM", "old log line leaks the throwable"),
        ("MEDIUM", "missing assertion in fallback test"), ("HIGH", "new 500 on GET /withdrawable")], 1)]
    answers({
        "F1": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.95, "severity": 2, "fix_is_mechanical": 0.2},
        "F2": {"introduced_by_this_diff": 0.8, "duplicate_of_prior_round": 0.9, "severity": 0, "fix_is_mechanical": 0.95},
        "F3": {"introduced_by_this_diff": 0.05, "duplicate_of_prior_round": 0.1, "severity": 1, "fix_is_mechanical": 0.9},
        "F4": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.2, "severity": 1, "fix_is_mechanical": 0.9},
        "F5": {"introduced_by_this_diff": 0.95, "duplicate_of_prior_round": 0.02, "severity": 2, "fix_is_mechanical": 0.3},
        "round": {"round_materially_same_as_previous": 0.3},
        "keystone": "F5",
    })
    res = ft.grade_round(fs, prior)
    g = {x["id"]: x for x in res["findings"]}
    assert [x["id"] for x in res["findings"] if x["duplicate"]] == ["F1", "F2"]
    assert [x["id"] for x in res["findings"] if x["pre_existing"]] == ["F3"]
    assert g["F3"]["noted_not_blocking"] and not g["F1"]["noted_not_blocking"]
    assert [x["id"] for x in res["findings"] if x["mechanical"]] == ["F2", "F3", "F4"]
    assert g["F1"]["severity"] == "HIGH" and g["F1"]["severity_jev"] == "HIGH" and g["F3"]["severity_jev"] == "MEDIUM"
    assert res["keystone"] == "F5" and res["same_as_previous_p"] == 0.3 and res["converged"] is False
    assert res["calls"] == 7 and res["input_tokens"] == 70, res


def test_convergence_over_two_rounds() -> None:
    r1 = [finding("F1", "HIGH", "reject() loses the audit row"), finding("F2", "MEDIUM", "no fallback test")]
    r2 = [finding("G1", "MEDIUM", "fallback test still thin"), finding("G2", "LOW", "comment wording")]
    answers({
        "F1": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.0, "severity": 2, "fix_is_mechanical": 0.1},
        "F2": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.0, "severity": 1, "fix_is_mechanical": 0.8},
        "G1": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.9, "severity": 1, "fix_is_mechanical": 0.9},
        "G2": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.1, "severity": 0, "fix_is_mechanical": 0.95},
        "round": {"round_materially_same_as_previous": 0.9},
        "keystone": "F1",
    })
    first = ft.grade_round(r1, [])
    assert first["same_as_previous_p"] is None and first["converged"] is False and first["calls"] == 3
    second = ft.grade_round(r2, r1)
    assert second["converged"] is True, second
    # a new HIGH in the round blocks convergence even when the round reads as "the same"
    answers({**json.loads((TMP / "answers.json").read_text()), "G2": {"introduced_by_this_diff": 0.9, "duplicate_of_prior_round": 0.1, "severity": 2, "fix_is_mechanical": 0.2}})
    assert ft.grade_round(r2, r1)["converged"] is False
    assert ft.converged(0.84, []) is False and ft.converged(0.85, []) is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests passed")
