"""Tests for Test Intent Escrow (Slice 1)."""

from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).parents[1] / "test_escrow.py"


def load_module():
    spec = importlib.util.spec_from_file_location("test_escrow", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SOURCE.parent))
    spec.loader.exec_module(module)
    return module


def test_load_diff():
    module = load_module()

    with tempfile.TemporaryDirectory() as directory:
        test_diff = Path(directory) / "test_dummy.diff"
        test_diff.write_text(
            "--- a/test_file.py\n+++ b/test_file.py\n- assert x == 1\n+ assert x > 0",
            encoding="utf-8",
        )
        content = module.load_diff_file(str(test_diff))
        assert "assert x > 0" in content


def test_jev_questions():
    module = load_module()

    questions = module.build_jev_questions()

    assert "intent" in questions
    assert questions["intent"]["type"] == "choice"
    assert "weakened" in questions["intent"]["criteria"]
    assert "protects" in questions["intent"]["criteria"]


STUB_JEV_CRASH = """#!/usr/bin/env python3
import sys
sys.stderr.write("Fatal authentication error: Bearer secret_leaked_key\\n")
sys.exit(2)
"""


def test_cli_error_sanitization():
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        (tmp / "jev").write_text(STUB_JEV_CRASH)
        (tmp / "jev").chmod(0o755)
        (tmp / "d.diff").write_text("- assert x == 1\n+ assert x > 0", encoding="utf-8")
        env = {**os.environ, "JEV_BIN": str(tmp / "jev"), "TYPESAFE_API_KEY": "stub_key"}
        res = subprocess.run([sys.executable, str(SOURCE), "--diff", str(tmp / "d.diff")],
                             capture_output=True, text=True, env=env, timeout=30)
        assert res.returncode == 1, res
        assert "secret_leaked_key" not in res.stdout + res.stderr, res.stderr
        assert "inspect provider access and limits locally" in res.stderr, res.stderr


def main():
    test_load_diff()
    test_jev_questions()
    test_cli_error_sanitization()
    print("All tests passed.")


if __name__ == "__main__":
    main()
