"""Offline check for the compaction advisor Stop hook, using a stub jev executable."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import compact_advisor as ca  # noqa: E402
import jev_patterns  # noqa: E402
import scope_sentinel as ss  # noqa: E402

ADVISOR = ROOT / "compact_advisor.py"
# Records argv and stdin and drops a marker, then answers from cfg.json (default: AC-4.1 answers).
STUB = """#!/usr/bin/env python3
import json, sys
from pathlib import Path
here = Path(__file__).parent
state = sys.stdin.read()
(here / "marker").write_text("called")
(here / "rec.json").write_text(json.dumps({"argv": sys.argv[1:], "stdin": state}))
cfg = json.loads((here / "cfg.json").read_text()) if (here / "cfg.json").exists() else {}
if cfg.get("stderr"):
    print(cfg["stderr"], file=sys.stderr)
if cfg.get("exit"):
    sys.exit(cfg["exit"])
a = {"switched_gears": 0.90, "at_boundary": 0.20, "needs_history": 0.40, "mid_operation": 0.10, **cfg}
print(json.dumps({"model": "typesafe/jev-stub-1", "answers": {
    "switched_gears": {"type": "noul", "noul": a["switched_gears"]},
    "at_boundary": {"type": "noul", "noul": a["at_boundary"]},
    "needs_history": {"type": "score", "score": a["needs_history"]},
    "mid_operation": {"type": "noul", "noul": a["mid_operation"]}},
    "usage": {"input_tokens": 33}}))
"""
PROMPTS = ["add login", "fix the test", "now write the changelog"]
AC41_OUT = (
    '{"systemMessage": "Recommended: compact now. Context is at 120k tokens. '
    'The task changed from \\"fix the test\\" to \\"now write the changelog\\". '
    'Run /compact with a short note to yourself, then continue."}'
)


def setup(tmp: Path, cfg: dict | None = None) -> None:
    (tmp / "jev").write_text(STUB)
    (tmp / "jev").chmod(0o755)
    if cfg is not None:
        (tmp / "cfg.json").write_text(json.dumps(cfg))


def write_lines(tmp: Path, lines: list) -> str:
    path = tmp / "t.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(path)


def claude_lines(
    prompts: list[str], usage: dict | None = None, extra: list | None = None
) -> list:
    usage = usage or {
        "input_tokens": 10_000,
        "cache_creation_input_tokens": 20_000,
        "cache_read_input_tokens": 85_000,
        "output_tokens": 5_000,
    }  # sums to 120 000
    lines = []
    for p in prompts:
        lines.append({"type": "user", "message": {"role": "user", "content": p}})
        lines.append(
            {
                "type": "assistant",
                "isSidechain": False,
                "message": {
                    "model": "claude-test-1",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "content": [{"type": "text", "text": f"did {p}"}],
                },
            }
        )
    lines.append(
        {
            "type": "assistant",
            "isSidechain": True,
            "message": {
                "usage": {"input_tokens": 999_999},
                "content": [{"type": "text", "text": "side"}],
            },
        }
    )
    lines[-2]["message"]["usage"] = usage  # newest main-chain entry
    return lines + (extra or [])


def codex_lines(prompts: list[str], total: int, window: int | None = 258_400) -> list:
    lines = [
        {"type": "event_msg", "payload": {"type": "user_message", "message": p}}
        for p in prompts
    ]
    lines.append(
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec"}}
    )
    lines.append(
        {
            "type": "response_item",
            "payload": {"type": "custom_tool_call", "name": "apply_patch"},
        }
    )
    lines.append(
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"total_tokens": total},
                    "model_context_window": window,
                    "total_token_usage": {"total_tokens": total * 3},
                },
            },
        }
    )
    return lines


def run(tmp: Path, host: str, event: dict, extra_env: dict | None = None):
    env = {
        **os.environ,
        "JEV_BIN": str(tmp / "jev"),
        "TYPESAFE_API_KEY": "stub",
        "CLAUDE_PROJECT_DIR": str(tmp),
        "SCOPE_SENTINEL": "1",
        **(extra_env or {}),
    }
    if "JEV_COMPACT_LINES" not in (extra_env or {}):
        env.pop("JEV_COMPACT_LINES", None)
    done = subprocess.run(
        [sys.executable, str(ADVISOR), "hook", host],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert done.returncode == 0, (done.returncode, done.stdout, done.stderr)
    log = tmp / ".local" / "compact.jsonl"
    rows = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    return done.stdout, rows


def event(tmp: Path, transcript, **more) -> dict:
    return {"session_id": "s1", "cwd": str(tmp), "transcript_path": transcript, **more}


def fresh():
    d = tempfile.TemporaryDirectory()
    return d, Path(d.name)


def check_claude_recommend() -> None:  # AC-4.1
    d, tmp = fresh()
    with d:
        setup(tmp)
        out, rows = run(
            tmp,
            "claude",
            event(tmp, write_lines(tmp, claude_lines(PROMPTS))),
            {"JEV_MODEL": "m-test"},
        )
        assert out.strip() == AC41_OUT, out
        r = rows[-1]
        assert (r["tier"], r["tokens"], r["window"], r["printed"]) == (
            "recommend",
            120000,
            None,
            True,
        ), r
        assert r["answers"]["needs_history"] == 0.4 and r["host"] == "claude", r
        assert (
            r["host_model"] == "claude-test-1"
            and r["jev_model"] == "typesafe/jev-stub-1"
        ), r
        assert (
            r["advisor_version"] == "advisor-v1" and r["lines"] == ca.DEFAULT_LINES
        ), r
        assert (
            r["input_tokens"] == 33
            and isinstance(r["elapsed"], float)
            and r["model"] == "m-test"
        ), r
        assert r["estimated_usd"] == r["input_tokens"] * jev_patterns.PRICE_PER_MILLION_INPUT / 1_000_000, r
        rec = json.loads((tmp / "rec.json").read_text())
        assert rec["argv"][rec["argv"].index("-m") + 1] == "m-test", rec["argv"]
        state = json.loads(rec["stdin"])
        assert list(state) == [
            "current_request",
            "previous_work",
            "recent_turn",
            "tools_this_turn",
        ], state
        assert (
            json.loads(rec["argv"][rec["argv"].index("-q") + 1]) == ca.COMPACT_QUESTIONS
        )
        assert rec["argv"][rec["argv"].index("-j") + 1] == "compact_advisor"
        assert state["recent_turn"] == "did now write the changelog", state


def check_stdin_message_and_tools() -> None:
    d, tmp = fresh()
    with d:
        setup(tmp)
        tool = {
            "type": "assistant",
            "isSidechain": False,
            "message": {
                "usage": {"input_tokens": 100_000},
                "content": [
                    {"type": "tool_use", "name": "Bash"},
                    {"type": "tool_use", "name": "Edit"},
                ],
            },
        }
        run(
            tmp,
            "claude",
            event(
                tmp,
                write_lines(tmp, claude_lines(PROMPTS, extra=[tool])),
                last_assistant_message="all green",
            ),
        )
        state = json.loads(json.loads((tmp / "rec.json").read_text())["stdin"])
        assert state["recent_turn"] == "all green" and state["tools_this_turn"] == [
            "Bash",
            "Edit",
        ], state
        run(
            tmp,
            "claude",
            event(tmp, write_lines(tmp, claude_lines(PROMPTS, extra=[tool]))),
        )
        state = json.loads(json.loads((tmp / "rec.json").read_text())["stdin"])
        assert state["recent_turn"] == "(tool calls only: Bash, Edit)", state


def check_codex() -> None:  # AC-4.2
    d, tmp = fresh()
    with d:
        setup(tmp)
        out, rows = run(
            tmp,
            "codex",
            event(
                tmp, write_lines(tmp, codex_lines(PROMPTS, 50_000)), model="gpt-test"
            ),
        )
        r = rows[-1]
        assert out == "" and not (tmp / "marker").exists(), out
        assert (r["tier"], r["reason"], r["window"], r["tokens"]) == (
            "silent",
            "below the notice line",
            258400,
            50000,
        ), r
        assert (
            r["host_model"] == "gpt-test"
            and r["answers"] is None
            and r["printed"] is False
        ), r
        out, rows = run(
            tmp, "codex", event(tmp, write_lines(tmp, codex_lines(PROMPTS, 170_000)))
        )
        msg = json.loads(out)["systemMessage"]
        assert msg.startswith(
            "Please compact before continuing. Context is at 170k tokens, 65.8% of the window. "
        ), msg
        assert rows[-1]["tier"] == "request" and rows[-1]["printed"] is True
        state = json.loads(json.loads((tmp / "rec.json").read_text())["stdin"])
        assert state["tools_this_turn"] == ["exec", "apply_patch"], state
    # A Codex subagent rollout has no typed prompt; the advisor must not borrow the root's (sentinel only).
    d, tmp = fresh()
    with d:
        setup(tmp)
        root, child = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"
        day = tmp / "sessions/2026/10/29"
        day.mkdir(parents=True)
        meta = lambda i, parent=None: {"type": "session_meta", "payload": {"id": i, **({"parent_thread_id": parent} if parent else {})}}
        (day / f"rollout-x-{root}.jsonl").write_text("\n".join(json.dumps(x) for x in [meta(root)] + codex_lines(PROMPTS, 1)))
        sub = day / f"rollout-x-{child}.jsonl"
        sub.write_text("\n".join(json.dumps(x) for x in [meta(child, root)] + codex_lines([], 170_000)))
        assert ss.latest_user_prompt(sub, "codex") == PROMPTS[-1], "the sentinel follows the parent"
        out, rows = run(tmp, "codex", event(tmp, str(sub)))
        assert out == "" and not (tmp / "marker").exists(), "a subagent Stop must not call Jev"
        assert (rows[-1]["tier"], rows[-1]["reason"]) == ("silent", "first request, nothing to move on from"), rows[-1]


def check_decide_tier() -> None:  # AC-4.3
    ans = {
        "switched_gears": {"noul": 0.90},
        "at_boundary": {"noul": 0.20},
        "needs_history": {"score": 0.40},
        "mid_operation": {"noul": 0.10},
    }
    state = ["a", "b"]  # the prompts, oldest first
    got = [
        ca.decide_tier(ans, t, ca.DEFAULT_LINES, state)[0]
        for t in (80_000, 109_999, 110_000, 159_999, 160_000)
    ]
    assert got == ["notice", "notice", "recommend", "recommend", "request"], got
    boundary = {
        "switched_gears": {"noul": 0.10},
        "at_boundary": {"noul": 0.70},
        "needs_history": {"score": 0.99},
        "mid_operation": {"noul": 0.10},
    }
    assert ca.decide_tier(boundary, 120_000, ca.DEFAULT_LINES, state) == (
        "recommend",
        "The last turn finished a unit of work and the next step needs little of the earlier context.",
    )
    boundary["needs_history"]["score"] = 1.0
    assert ca.decide_tier(boundary, 120_000, ca.DEFAULT_LINES, state) == (
        "silent",
        "same work continuing",
    )
    ans["mid_operation"]["noul"] = 0.61
    assert ca.decide_tier(ans, 120_000, ca.DEFAULT_LINES, state) == (
        "silent",
        "mid operation",
    )
    d, tmp = fresh()
    with d:
        setup(tmp)
        out, rows = run(
            tmp,
            "claude",
            event(
                tmp, write_lines(tmp, claude_lines(PROMPTS, {"input_tokens": 79_999}))
            ),
        )
        r = rows[-1]
        assert out == "" and not (tmp / "marker").exists(), out
        assert (r["tier"], r["reason"]) == ("silent", "below the notice line"), r


def check_helpers() -> None:
    assert ca.trunc("abc", 3) == "abc" and ca.trunc("abcd", 3) == "ab…"
    os.environ["JEV_COMPACT_LINES"] = "1000,2000,3000"
    try:
        assert ca.lines_from_env() == {
            "notice": 1000,
            "recommend": 2000,
            "request": 3000,
        }
        os.environ["JEV_COMPACT_LINES"] = "nonsense"
        assert ca.lines_from_env() == ca.DEFAULT_LINES
    finally:
        del os.environ["JEV_COMPACT_LINES"]
    assert ca.tier_message("silent", "r", 1, None) is None
    assert ca.tier_message("notice", "R.", 80_000, 200_000) == (
        "Context is at 80k tokens, 40.0% of the window. R. Compacting is optional. "
        "If you do, run /compact with a short note to yourself."
    )


def check_skips_and_errors() -> None:  # AC-4.4
    d, tmp = fresh()
    with d:
        setup(tmp, {"mid_operation": 0.80})
        out, rows = run(
            tmp, "claude", event(tmp, write_lines(tmp, claude_lines(PROMPTS)))
        )
        assert out == "" and (rows[-1]["tier"], rows[-1]["reason"]) == (
            "silent",
            "mid operation",
        ), rows[-1]
    d, tmp = fresh()
    with d:
        setup(tmp)
        out, rows = run(
            tmp, "claude", event(tmp, write_lines(tmp, claude_lines(PROMPTS[:1])))
        )
        assert out == "" and not (tmp / "marker").exists()
        assert (rows[-1]["tier"], rows[-1]["reason"]) == (
            "silent",
            "first request, nothing to move on from",
        ), rows[-1]
    d, tmp = fresh()
    with d:
        setup(tmp, {"exit": 1})
        out, rows = run(
            tmp, "claude", event(tmp, write_lines(tmp, claude_lines(PROMPTS)))
        )
        assert out == "" and rows[-1].get("error") and rows[-1]["printed"] is False, (
            rows
        )
    d, tmp = fresh()
    with d:
        setup(tmp, {"exit": 2, "stderr": "curl: (22) HTTP 429 key ts_secret1234567890abcdef"})
        out, rows = run(
            tmp, "claude", event(tmp, write_lines(tmp, claude_lines(PROMPTS)))
        )
        err = rows[-1]["error"]
        assert "jev exited 2" in err and "HTTP 429" in err and "ts_secret1234567890abcdef" not in err, rows[-1]
    d, tmp = fresh()
    with d:
        setup(tmp)
        out, rows = run(tmp, "codex", event(tmp, None))
        assert out == "" and rows[-1]["error"] == "no transcript", rows
        out, _ = run(tmp, "claude", {})  # empty event: still exit 0, no stdout
        assert out == ""
    d, tmp = fresh()
    with d:
        setup(tmp)
        many = [f"task {i}" for i in range(30)] + ["latest"]
        run(tmp, "claude", event(tmp, write_lines(tmp, claude_lines(many))))
        prev = json.loads(json.loads((tmp / "rec.json").read_text())["stdin"])[
            "previous_work"
        ].split("\n")
        assert prev == [f"task {i}" for i in range(10, 30)], prev


def check_scan_keys() -> None:
    d, tmp = fresh()
    with d:
        summary = {
            "type": "user",
            "isCompactSummary": True,
            "message": {"content": "earlier we did X"},
        }
        lines = [summary] + claude_lines(PROMPTS)
        scan = ss.scan_transcript(Path(write_lines(tmp, lines)), "claude")
        assert (
            scan["prompts"] == PROMPTS and scan["compact_summary"] == "earlier we did X"
        ), scan
        assert scan["tokens"] == 120000 and scan["window"] is None, scan
        assert scan["last_assistant_text"] == "did now write the changelog", scan
        assert ss.scan_transcript(Path(write_lines(tmp, [])), "claude")["tokens"] == 0
        agy = ss.scan_transcript(Path(write_lines(tmp, [])), "agy")
        assert "tokens" not in agy, agy


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("check_"):
            fn()
            print("ok", name)
