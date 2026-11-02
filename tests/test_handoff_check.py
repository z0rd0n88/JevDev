"""Tests for Handoff Integrity Check with offline stub Jev execution."""

import json
import os
from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).parents[1] / "handoff_check.py"

def load_module():
    spec = importlib.util.spec_from_file_location("handoff_check", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SOURCE.parent))
    spec.loader.exec_module(module)
    return module


def test_parse_ledger():
    module = load_module()
    content = """# Title Header
# Another comment

- Constraint 1: Use TLS
* Constraint 2: Maintain SQLite index

Constraint 3: No unauthenticated endpoints
"""
    items = module.parse_ledger(content)
    assert len(items) == 3
    assert items[0].line_num == 4
    assert items[0].text == "Constraint 1: Use TLS"
    assert items[1].line_num == 5
    assert items[1].text == "Constraint 2: Maintain SQLite index"
    assert items[2].line_num == 7
    assert items[2].text == "Constraint 3: No unauthenticated endpoints"


def test_load_file_and_limits():
    module = load_module()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        normal = tmp / "normal.txt"
        normal.write_text("hello world", encoding="utf-8")
        assert module.load_file(str(normal)) == "hello world"

        # Non-existent
        try:
            module.load_file(str(tmp / "nonexistent.txt"))
            assert False, "Should raise FileNotFoundError"
        except FileNotFoundError:
            pass

        # Symlink
        sym = tmp / "symlink.txt"
        sym.symlink_to(normal)
        try:
            module.load_file(str(sym))
            assert False, "Should reject symlinks by default"
        except PermissionError:
            pass


def test_redaction():
    module = load_module()
    raw = "Deploy with GH_TOKEN=ghp_secrettoken123456789 and Bearer sk-abcdefghij0123456789xyz"
    scrubbed = module.redact(raw)
    assert "ghp_" not in scrubbed
    assert "sk-" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_build_jev_questions():
    module = load_module()
    items = [module.LedgerItem(line_num=1, text="Enforce auth")]
    q = module.build_jev_questions(items)
    assert "item_0" in q
    assert q["item_0"]["type"] == "choice"
    assert "<constraint>Enforce auth</constraint>" in q["item_0"]["instructions"]
    assert "intact" in q["item_0"]["criteria"]
    assert "missing" in q["item_0"]["criteria"]


def test_isolated_env():
    module = load_module()
    original_env = os.environ.copy()
    try:
        os.environ["GH_TOKEN"] = "ghp_leaked_token"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "aws_secret"
        os.environ["TYPESAFE_API_KEY"] = "safe_jev_key"

        env = module.get_isolated_env()
        assert "TYPESAFE_API_KEY" in env
        assert "GH_TOKEN" not in env
        assert "AWS_SECRET_ACCESS_KEY" not in env

        # Missing key raises
        del os.environ["TYPESAFE_API_KEY"]
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        try:
            module.get_isolated_env()
            assert False, "Should raise when no API key"
        except RuntimeError:
            pass
    finally:
        os.environ.clear()
        os.environ.update(original_env)


STUB_JEV_INTACT = """#!/usr/bin/env python3
import json, sys
state = sys.stdin.read()
assert "<untrusted_handoff>" in state, "Handoff must be framed in XML"
assert "ghp_" not in state, "Secrets must be redacted"
response = {
    "answers": {
        "item_0": {
            "choice": "intact",
            "probabilities": {"intact": 0.98, "missing": 0.01, "changed": 0.01}
        }
    },
    "usage": {"input_tokens": 120}
}
print(json.dumps(response))
"""

STUB_JEV_VIOLATION = """#!/usr/bin/env python3
import json, sys
response = {
    "answers": {
        "item_0": {
            "choice": "missing",
            "probabilities": {"intact": 0.05, "missing": 0.92, "changed": 0.03}
        }
    },
    "usage": {"input_tokens": 120}
}
print(json.dumps(response))
"""

STUB_JEV_CRASH = """#!/usr/bin/env python3
import sys
sys.stderr.write("Fatal authentication error: Bearer secret_leaked_key\\n")
sys.exit(2)
"""


def run_cli_test(tmp: Path, stub_script: str, ledger_text: str, handoff_text: str, *extra_flags):
    jev_path = tmp / "jev"
    jev_path.write_text(stub_script)
    jev_path.chmod(0o755)

    ledger_path = tmp / "ledger.txt"
    ledger_path.write_text(ledger_text, encoding="utf-8")

    handoff_path = tmp / "handoff.txt"
    handoff_path.write_text(handoff_text, encoding="utf-8")

    env = {
        **os.environ,
        "JEV_BIN": str(jev_path),
        "TYPESAFE_API_KEY": "stub_key",
    }

    cmd = [sys.executable, str(SOURCE), "--ledger", str(ledger_path), "--handoff", str(handoff_path), *extra_flags]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_cli_intact_and_json():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger = "Constraint 1: Enforce TLS"
        handoff = "We strictly enforced TLS across all endpoints with ghp_fake_token."

        # Plain run
        res = run_cli_test(tmp, STUB_JEV_INTACT, ledger, handoff)
        assert res.returncode == 0, f"Stdout: {res.stdout}\nStderr: {res.stderr}"
        assert "[INTACT] (conf: 0.98)" in res.stdout
        assert "Tokens: 120" in res.stdout

        # JSON mode
        res_json = run_cli_test(tmp, STUB_JEV_INTACT, ledger, handoff, "--json")
        assert res_json.returncode == 0
        data = json.loads(res_json.stdout)
        assert data["violations_count"] == 0
        assert data["results"][0]["verdict"] == "intact"
        assert data["results"][0]["confidence"] == 0.98


def test_cli_violation_and_strict():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger = "Constraint 1: Enforce TLS"
        handoff = "Handoff text dropping TLS completely."

        # Regular violation (exit code 1)
        res = run_cli_test(tmp, STUB_JEV_VIOLATION, ledger, handoff)
        assert res.returncode == 1, "Violations must exit with code 1"
        assert "[MISSING] (conf: 0.92)" in res.stdout
        assert "Integrity violation detected" in res.stdout

        # Strict mode (exit code 2)
        res_strict = run_cli_test(tmp, STUB_JEV_VIOLATION, ledger, handoff, "--strict")
        assert res_strict.returncode == 2, "Strict violations must exit with code 2"


def test_cli_error_sanitization():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger = "Constraint 1: Enforce TLS"
        handoff = "Handoff text"

        res = run_cli_test(tmp, STUB_JEV_CRASH, ledger, handoff)
        assert res.returncode == 1
        assert "secret_leaked_key" not in res.stderr
        assert "secret_leaked_key" not in res.stdout
        assert "inspect provider access and limits locally" in res.stderr


def main():
    test_parse_ledger()
    test_load_file_and_limits()
    test_redaction()
    test_build_jev_questions()
    test_isolated_env()
    test_cli_intact_and_json()
    test_cli_violation_and_strict()
    test_cli_error_sanitization()
    print("All tests passed.")


if __name__ == "__main__":
    main()
