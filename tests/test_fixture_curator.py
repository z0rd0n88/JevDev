"""Tests for the Benchmark Fixture Curator."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).parents[1] / "fixture_curator.py"

def load_module():
    spec = importlib.util.spec_from_file_location("fixture_curator", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SOURCE.parent))
    spec.loader.exec_module(module)
    return module

def test_deterministic_checks():
    module = load_module()
    
    # Missing fields
    bad_record = {"text": "foo"}
    errors = module.validate_record(bad_record)
    assert "Missing required field: id" in errors, f"Got: {errors}"
    assert "Missing required field: gold" in errors
    
    
    # Valid record
    good_record = {"id": "123", "text": "do something", "gold": "some_skill"}
    assert not module.validate_record(good_record)
    
    # Null gold is allowed
    null_gold_record = {"id": "456", "text": "hello", "gold": None}
    assert not module.validate_record(null_gold_record)

    # Null id/text, blank text, and wrong types are not
    for bad in ({"id": None, "text": "a", "gold": "x"}, {"id": "1", "text": None, "gold": "x"},
                {"id": "1", "text": "   ", "gold": "x"}, {"id": 1, "text": "a", "gold": "x"},
                {"id": "1", "text": "a", "gold": ["x", "y"]}):
        assert module.validate_record(bad), bad
    assert module.validate_record([1, 2]) == ["Record is not a JSON object"]

def test_duplicate_ids():
    module = load_module()
    
    records = [
        {"id": "1", "text": "a", "gold": "x"},
        {"id": "2", "text": "b", "gold": "y"},
        {"id": "1", "text": "c", "gold": "z"}
    ]
    dupes = module.find_duplicates(records)
    assert "1" in dupes
    assert "2" not in dupes

def test_jev_questions_format():
    module = load_module()
    
    # Test that the question structure aligns with our expectations for Jev
    questions = module.build_curator_questions()
    
    assert "self_contained" in questions
    assert questions["self_contained"]["type"] == "noul"
    
    assert "multiple_defensible" in questions
    assert questions["multiple_defensible"]["type"] == "noul"

STUB = """#!/usr/bin/env python3
import json, sys
text = sys.stdin.read()
if "NAN" in text:
    print('{"answers": {"self_contained": {"noul": NaN}, "multiple_defensible": {"noul": 0.1}}}')
elif "BROKEN" in text:
    print(json.dumps({"answers": {"self_contained": {"error": "x"}, "multiple_defensible": {"noul": 0.1}}}))
else:
    vague = "that file" in text
    print(json.dumps({"answers": {"self_contained": {"noul": 0.1 if vague else 0.9},
                                  "multiple_defensible": {"noul": 0.9}},
                      "usage": {"input_tokens": None}}))
"""


def run_cli(tmp, rows, *extra):
    fixture = tmp / "f.jsonl"
    fixture.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n")
    env = {**os.environ, "JEV_BIN": str(tmp / "jev"), "TYPESAFE_API_KEY": "stub"}
    done = subprocess.run([sys.executable, str(SOURCE), str(fixture), *extra],
                          capture_output=True, text=True, env=env)
    return done.returncode, done.stdout


def test_cli():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "jev").write_text(STUB)
        (tmp / "jev").chmod(0o755)
        ok = {"id": "a", "text": "Write a haiku about rain.", "gold": None}
        vague = {"id": "b", "text": "fix the bug in that file", "gold": "debugging"}

        rc, out = run_cli(tmp, [ok, vague])
        assert rc == 0, out
        assert "Evaluating 1/2: a... OK" in out, "null gold must skip the ambiguity flag"
        assert "Not self-contained" in out and "Multiple labels defensible" in out, out
        assert "Flagged 1/2 prompts for human review; 0 failed." in out, out

        rc, out = run_cli(tmp, [ok, {"id": "c", "text": "BROKEN", "gold": None}])
        assert rc == 1 and "1 failed" in out, "a missing Jev answer must fail, not become a verdict"

        rc, out = run_cli(tmp, [ok, {"id": "n", "text": "NAN", "gold": None}])
        assert rc == 1 and "invalid self_contained score" in out, "a NaN score must fail, not pass as OK"
        assert run_cli(tmp, [ok, "{not json"], "--skip-jev")[0] == 1, "invalid JSON must fail"
        assert run_cli(tmp, [ok, "[" * 100000], "--skip-jev")[0] == 1, "deep nesting must fail cleanly"
        assert run_cli(tmp, [ok, "[1, 2]"], "--skip-jev")[0] == 1, "non-object line must fail"
        assert run_cli(tmp, [{"id": 1, "text": "a", "gold": None}] * 2, "--skip-jev")[0] == 1
        assert run_cli(tmp, [], "--skip-jev")[0] == 1, "empty fixture must fail"
        (tmp / "jev").unlink()
        rc, out = run_cli(tmp, [ok])
        assert rc == 1 and "1 failed" in out, "a dead jev must not look like a clean pass"


def main():
    test_deterministic_checks()
    test_duplicate_ids()
    test_jev_questions_format()
    test_cli()
    print("All tests passed.")

if __name__ == "__main__":
    main()
