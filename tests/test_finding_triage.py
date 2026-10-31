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
    assert fs[0]["locations"] == [("a/B.kt", 317, 322)], fs[0]["locations"]  # en dash ranges keep their end line
    assert fs[1]["locations"] == [("docs/x.md", 4, 4)]


def test_parses_finding_fixer_report_lines() -> None:
    text = "F1  fix-here                    applied   now rejects\nF3  refuted                     no edit   unreachable\nnot a line\n"
    assert ft.parse_fixer_report(text) == {"F1": {"ruling": "fix-here", "action": "applied", "note": "now rejects"}, "F3": {"ruling": "refuted", "action": "no edit", "note": "unreachable"}}


def test_redacts_tokens() -> None:
    assert ft.redact("x ghp_abcdefghijklmnop y Bearer abcdefghijklmnop.q") == "x [REDACTED] y [REDACTED]"
    cases = {
        "TYPESAFE_API_KEY=vck_FAKEFAKEFAKEFAKE1234": "TYPESAFE_API_KEY=[REDACTED]",
        "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEFghiJKL": "jwt [REDACTED]",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE\nabc\n-----END RSA PRIVATE KEY-----": "[REDACTED]",
        "password: hunter2hunter2hunter2": "password: [REDACTED]",
        'DISCORD_BOT_TOKEN="MTIzNDU2Nzg5MDEyMzQ1Njc4OTA"': 'DISCORD_BOT_TOKEN="[REDACTED]"',
        "postgres://alex:s3cretpassw0rd@db.local/x": "postgres://[REDACTED]@db.local/x",
        "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE": "[REDACTED]",
    }
    for raw, want in cases.items():
        assert ft.redact(raw) == want, (raw, ft.redact(raw))
    doc = {"body": 'token="ghp_abcdefghijklmnop", pw=password=abcdefghijklmn0p; ok', "n": 1}
    out = json.loads(ft.redact(json.dumps(doc)))  # redacting a JSON document keeps it parseable
    assert out["n"] == 1 and "ghp_" not in out["body"] and "abcdefghijklmn0p" not in out["body"], out
    assert ft.redact("password=abcdefghijklmnop") == "password=abcdefghijklmnop"  # no digit: treated as a word, not a secret
    for plain in ("WithdrawalService.kt:1224-1231 reads skip_question and the ok_token", "ask_jev_files.py files -q ask-jev", "token: WITHDRAWAL_STORE_UNAVAILABLE is the 503 vocabulary"):
        assert ft.redact(plain) == plain, ft.redact(plain)


def test_resolves_bare_paths_and_reads_blame_from_a_repo() -> None:
    import subprocess

    repo = TMP / "repo"
    (repo / "a").mkdir(parents=True)
    (repo / "b").mkdir()
    (repo / "a/Same.kt").write_text("one\ntwo\nthree\n")
    (repo / "b/Same.kt").write_text("x\n")
    (repo / "Only.kt").write_text("l1\nl2\nl3\nl4\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x", "PATH": os.environ["PATH"], "HOME": str(TMP)}
    for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "one"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, env=env, capture_output=True, text=True).stdout.strip()
    assert ft.resolve_path(repo, sha, "Same.kt") is None  # ambiguous: two files share the basename
    assert ft.resolve_path(repo, sha, "Only.kt") == "Only.kt"
    assert ft.resolve_path(repo, sha, "Missing.kt") is None
    assert ft.resolve_path(repo, sha, "a/Same.kt") == "a/Same.kt"
    now = ft.datetime.now(ft.timezone.utc)
    b = ft.blame(repo, sha, "Only.kt", 2, 3, {sha}, now)
    assert b["lines"] == 2 and b["written_in_this_change"] == 1.0 and b["median_age_days"] == 0, b
    assert ft.hunk(repo, sha, "Only.kt", 2, 2, context=1) == "1: l1\n2: l2\n3: l3"
    ambiguous = {**finding("F1", "LOW", "x"), "locations": [("Same.kt", 1, 1)]}
    state = ft.finding_state(ambiguous, [], repo, sha, {sha}, now)
    assert state["blame"] is None and state["hunk"] == "" and "ambiguous" in state["state_error"], state
    missing = {**finding("F2", "LOW", "x"), "locations": [("Only.kt", 40, 41)]}
    state = ft.finding_state(missing, [], repo, sha, {sha}, now)
    assert state["blame"] is None and "unreadable" in state["state_error"], state
    good = {**finding("F3", "LOW", "x"), "locations": [("Only.kt", 1, 2)]}
    state = ft.finding_state(good, [], repo, sha, {sha}, now)
    assert state["state_error"] is None and state["blame"]["lines"] == 2 and state["hunk"].startswith("1: l1"), state
    assert ft.finding_state(finding("F4", "LOW", "x"), [], repo, sha, {sha}, now)["state_error"] == "no location cited"


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
    # no fixture row cites a location, so there is no blame evidence and nothing may be called pre-existing
    assert [x["id"] for x in res["findings"] if x["pre_existing"]] == [] and not any(x["noted_not_blocking"] for x in res["findings"])
    assert all(x["blame"] is None and x["state_error"] == "no location cited" for x in res["findings"])
    f3 = {"introduced_by_this_diff": {"noul": 0.05}, "duplicate_of_prior_round": {"noul": 0.1}, "severity": {"score": 1}, "fix_is_mechanical": {"noul": 0.9}}
    assert ft.label(f3, has_blame=True)["pre_existing"] is True and ft.label(f3, has_blame=True)["noted_not_blocking"] is True
    assert ft.label(f3, has_blame=False)["pre_existing"] is False
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
    # the same new HIGH, once the skeptic refuted it, no longer keeps the loop open
    r2[1]["verdict"] = "REFUTED"
    assert ft.grade_round(r2, r1)["converged"] is True
    assert ft.converged(0.84, []) is False and ft.converged(0.85, []) is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests passed")
