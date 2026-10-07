"""Offline check for the Scope Sentinel shadow hook, using a stub jev executable."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).parents[1] / "scope_sentinel.py"
STUB = """#!/usr/bin/env python3
import json, sys
state = sys.stdin.read()
assert "do not push" in state and "git push origin main" in state, state
print(json.dumps({"answers": {"scope": {"choice": "conflict",
    "probabilities": {"covered": 0.05, "ambiguous": 0.15, "conflict": 0.8}}},
    "usage": {"input_tokens": 42}}))
"""


def run_hook(tmp: Path, event: dict) -> None:
    env = {
        **os.environ,
        "JEV_BIN": str(tmp / "jev"),
        "TYPESAFE_API_KEY": "stub",
        "CLAUDE_PROJECT_DIR": str(tmp),
    }
    done = subprocess.run(
        [sys.executable, str(SOURCE), "hook"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
    )
    assert done.returncode == 0 and done.stdout == "", (
        done.returncode,
        done.stdout,
        done.stderr,
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "jev").write_text(STUB)
        (tmp / "jev").chmod(0o755)
        transcript = tmp / "t.jsonl"
        transcript.write_text(
            "\n".join(
                json.dumps(e)
                for e in [
                    {"type": "user", "message": {"content": "old request"}},
                    {
                        "type": "user",
                        "message": {"content": "Review the branch, do not push."},
                    },
                    {
                        "type": "user",
                        "isMeta": True,
                        "message": {"content": "meta noise"},
                    },
                    {
                        "type": "user",
                        "message": {"content": "<command-name>/effort</command-name>"},
                    },
                    {
                        "type": "user",
                        "message": {
                            "content": [{"type": "tool_result", "content": "x"}]
                        },
                    },
                ]
            )
        )
        log = tmp / ".local" / "sentinel.jsonl"
        base = {
            "session_id": "s1",
            "transcript_path": str(transcript),
            "tool_name": "Bash",
        }

        run_hook(tmp, {**base, "tool_input": {"command": "git status"}})
        assert not log.exists(), "safe command must not be judged"

        run_hook(tmp, {**base, "tool_input": {"command": "git push origin main"}})
        row = json.loads(log.read_text())
        assert row["instruction"] == "Review the branch, do not push.", row
        assert row["result"] == "conflict" and row["confidence"] == 0.8, row
        assert row["sentinel_version"] == "shadow-v1" and "error" not in row, row

        (tmp / "jev").unlink()
        run_hook(tmp, {**base, "tool_input": {"command": "git push origin main"}})
        rows = log.read_text().splitlines()
        assert len(rows) == 2 and "error" in json.loads(rows[1]), (
            "jev failure must fail open and log"
        )
    print("sentinel hook ok")


if __name__ == "__main__":
    main()
