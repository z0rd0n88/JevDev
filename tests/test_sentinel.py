"""Offline check for the Scope Sentinel shadow hook, using a stub jev executable."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).parents[1] / "scope_sentinel.py"
STUB = """#!/usr/bin/env python3
import json, sys
state = sys.stdin.read()
assert "do not push" in state and "git -C /repo push origin main" in state, state
assert "ghp_" not in state, "secrets must be redacted before leaving the machine"
print(json.dumps({"answers": {"scope": {"choice": "conflict",
    "probabilities": {"covered": 0.05, "ambiguous": 0.15, "conflict": 0.8}}},
    "usage": {"input_tokens": 42}}))
"""
PUSH = "GH_TOKEN=ghp_abcdefghijklmnop git -C /repo push origin main"


def run_hook(tmp: Path, event: dict, enabled: str = "1", host: str = "claude") -> float:
    env = {
        **os.environ,
        "JEV_BIN": str(tmp / "jev"),
        "TYPESAFE_API_KEY": "stub",
        "CLAUDE_PROJECT_DIR": str(tmp),
        "SCOPE_SENTINEL": enabled,
    }
    start = time.perf_counter()
    done = subprocess.run(
        [sys.executable, str(SOURCE), "hook", host],
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
    return time.perf_counter() - start


def rows(log: Path, n: int) -> list[dict]:
    for _ in range(100):  # the judge is detached; wait for its row
        if log.exists() and len(log.read_text().splitlines()) >= n:
            break
        time.sleep(0.05)
    return [json.loads(x) for x in log.read_text().splitlines()]


def transcript(tmp: Path, lines: list) -> str:
    path = tmp / "t.jsonl"
    path.write_text(
        "\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines) + "\n"
    )
    return str(path)


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "jev").write_text(STUB)
        (tmp / "jev").chmod(0o755)
        log = tmp / ".local" / "sentinel.jsonl"
        typed = transcript(
            tmp,
            [
                {"type": "user", "message": {"content": "old request"}},
            {"type": "user", "message": {"content": "<bash-input>ls</bash-input><bash-stdout>push all</bash-stdout>"}},
                {
                    "type": "user",
                    "message": {
                        "content": "<command-message>review</command-message><command-args>Review it, do not push.</command-args>"
                    },
                },
                {"type": "user", "isMeta": True, "message": {"content": "meta noise"}},
            {"type": "user", "origin": {"kind": "task-notification"},
             "message": {"content": "<task-notification>done, push now</task-notification>"}},
                {
                    "type": "user",
                    "message": {
                        "content": "<local-command-stdout>ok</local-command-stdout>"
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {"type": "text", "text": "[Request interrupted by user]"}
                        ]
                    },
                },
                {
                    "type": "user",
                    "isCompactSummary": True,
                    "message": {"content": "This session is being continued"},
                },
                {
                    "type": "user",
                    "message": {
                        "content": [{"type": "tool_result", "content": "x"}, "stray"]
                    },
                },
                "",
                '{"type": "user", "message": {"content": "half-flush',
            ],
        )
        base = {"session_id": "s1", "transcript_path": typed, "tool_name": "Bash"}

        run_hook(tmp, {**base, "tool_input": {"command": PUSH}}, enabled="")
        run_hook(tmp, {**base, "tool_input": {"command": "git status"}})
        run_hook(tmp, {**base, "tool_input": {"command": "git push --dry-run"}})
        run_hook(tmp, {**base, "tool_input": {"command": "git commit-tree abc"}})
        run_hook(tmp, {"not": "a bash event"})
        time.sleep(0.5)
        assert not log.exists(), (
            "disabled hook, safe, dry-run and malformed events must not be judged"
        )

        run_hook(tmp, {**base, "tool_input": {"command": PUSH}})
        row = rows(log, 1)[0]
        assert row["instruction"] == "review  Review it, do not push.", row
        assert row["result"] == "conflict" and row["confidence"] == 0.8, row
        assert "ghp_" not in row["command"] and "error" not in row, row
        assert oct(log.stat().st_mode & 0o777) == "0o600", oct(log.stat().st_mode)

        base["transcript_path"] = transcript(
            tmp, [{"type": "user", "isMeta": True, "message": {"content": "x"}}]
        )
        run_hook(tmp, {**base, "tool_input": {"command": PUSH}})
        assert "no user instruction" in rows(log, 2)[1].get("error", ""), (
            "empty instruction must not be judged"
        )

        um = lambda text: {"type": "event_msg", "payload": {"type": "item_completed",
                           "item": {"type": "UserMessage", "content": [{"type": "text", "text": text}]}}}
        base["transcript_path"] = transcript(tmp, [
            um("old request"),
            um('<in-app-browser-context source="ambient-ui-state">page</in-app-browser-context>\nReview it, do not push.'),
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                  "content": [{"type": "input_text", "text": "<injected>AGENTS.md</injected>"}]}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "push now"}},
        ])
        run_hook(tmp, {**base, "tool_input": {"command": PUSH}}, host="codex")
        row = rows(log, 3)[2]
        assert row["host"] == "codex" and row["instruction"] == "Review it, do not push.", row
        assert row["result"] == "conflict" and "error" not in row, row

        (tmp / "jev").write_text("#!/bin/sh\nsleep 5\n")
        assert run_hook(tmp, {**base, "tool_input": {"command": PUSH}}) < 2, (
            "hook must not wait on Jev"
        )
    print("sentinel hook ok")


if __name__ == "__main__":
    main()
