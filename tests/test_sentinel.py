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


def check_key_only() -> None:
    """with_jev_key.sh passes the Jev key from the secrets file and nothing else."""
    with tempfile.TemporaryDirectory() as home:
        Path(home, ".secr" + "ets").write_text(
            "export GH_TOKEN=ghp_should_not_leak\nexport TYPESAFE_API_KEY=jev-key\nRUNPOD_API_KEY=nope\n")
        env = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "GH_TOKEN", "RUNPOD_API_KEY")}
        done = subprocess.run(["bash", str(SOURCE.parent / "with_jev_key.sh"), "env"],
                              capture_output=True, text=True, env={**env, "HOME": home})
        assert done.returncode == 0, done.stderr
        assert "TYPESAFE_API_KEY=jev-key" in done.stdout.splitlines(), "Jev key must be passed"
        assert "ghp_should_not_leak" not in done.stdout and "RUNPOD_API_KEY" not in done.stdout, "other secrets leaked"


def check_patterns() -> None:
    """Risky-command and redaction rules, including the forms earlier reviews found missing or mangled."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("scope_sentinel", SOURCE)
    sentinel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sentinel)
    risky = ["gh --repo=o/r pr merge 1", 'git -C "/a b" push', "git stash clear", "git restore .",
             "git branch --delete --force x", "rm -v -rf /x", "gh api --method DELETE repos/x",
             "git commit -m x && git push --dry-run", "git push --force; echo --dry-run"]
    safe = ["git push --dry-run", "git commit-tree abc", "git branch -d x", "git restore-thing", "cat deploy.md"]
    assert [c for c in risky if not sentinel.is_risky(c)] == [], "risky form missed"
    assert [c for c in safe if sentinel.is_risky(c)] == [], "safe form judged"
    secrets = {"mysql --password hunter2": "hunter2", "curl -u user:hunter2 u": "hunter2",
               'curl -d \'{"token": "abc123"}\'': "abc123", "AKIAIOSFODNN7EXAMPLE": "AKIA",
               "xoxb-123456789012-abcdefghij": "xoxb", "glpat-abcdefghij1234567890": "glpat"}
    for text, secret in secrets.items():
        assert secret not in sentinel.redact(text), text
    for text in ("git commit -m 'fix bearer token parsing'", "git checkout sk-feature-branch-name"):
        assert sentinel.redact(text) == text, "ordinary text must not be redacted"
    assert sentinel.redact("https://u:pw@host") == "https://u:[REDACTED]@host"
    start = time.perf_counter()
    for text in ("git -C " * 20000, "gh -R " * 20000, 'git -C "' * 20000, "find " * 20000):
        sentinel.is_risky(text)
    assert time.perf_counter() - start < 2, "risky check must stay fast on long commands"


def main() -> None:
    check_patterns()
    check_key_only()
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
        assert row["constraint_files"] == ["AGENTS.md"], "the repo's AGENTS.md must reach Jev as constraints"
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

        req = lambda text: {"type": "USER_INPUT", "source": "USER_EXPLICIT",
                            "content": f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>"}
        agy_transcript = transcript(tmp, [req("old request"), req("Review it, do not push."),
                                          {"type": "PLANNER_RESPONSE", "content": "push now"}])
        agy_event = {"conversationId": "c1", "transcriptPath": agy_transcript,
                     "toolCall": {"name": "run_command", "args": {"CommandLine": PUSH, "Cwd": str(tmp)}}}
        run_hook(tmp, {**agy_event, "toolCall": {"name": "view_file", "args": {"CommandLine": PUSH}}}, host="agy")
        run_hook(tmp, agy_event, host="agy")
        row = rows(log, 4)[3]
        time.sleep(0.5)
        assert len(log.read_text().splitlines()) == 4, "a non-shell agy tool must not be judged"
        assert row["host"] == "agy" and row["session_id"] == "c1", row
        assert row["instruction"] == "Review it, do not push." and row["result"] == "conflict", row

        import fcntl
        held = []
        for i in range(4):
            held.append(open(log.parent / f".judge-{i}.lock", "w"))
            fcntl.flock(held[-1], fcntl.LOCK_EX | fcntl.LOCK_NB)
        n = len(log.read_text().splitlines())
        run_hook(tmp, {**base, "transcript_path": transcript(tmp, [{"type": "user", "message": {"content": "do not push"}}]),
                      "tool_input": {"command": PUSH}})
        assert "skipped: 4 judges" in rows(log, n + 1)[n].get("error", ""), "a fifth judge must not call Jev"
        for handle in held:
            handle.close()

        (tmp / "jev").write_text("#!/bin/sh\nsleep 5\n")
        assert run_hook(tmp, {**base, "tool_input": {"command": PUSH}}) < 2, (
            "hook must not wait on Jev"
        )
    print("sentinel hook ok")


if __name__ == "__main__":
    main()
