#!/usr/bin/env python3
"""Compaction advisor for Claude/Codex Stop and Antigravity PostInvocation hooks.

Port of ten-levels-of-jev level07 should-compact.ts. Prints {"systemMessage": ...} or nothing, never plain text.
"""

import json
import os
from pathlib import Path
import sys
import time

from jev_patterns import DEFAULT_MODEL, call as jev_call
from scope_sentinel import (
    append_row,
    host_model,
    log_dir,
    project_hooked,
    redact,
    repo_root,
    scan_transcript,
)

ADVISOR_VERSION = "advisor-v2"
# ponytail: absolute-token lines assume a ~200k window (55% / 80% rule); set JEV_COMPACT_LINES for larger windows.
DEFAULT_LINES = {"notice": 80_000, "recommend": 110_000, "request": 160_000}
PREVIOUS_PROMPTS = (
    20  # ponytail: upstream joins every earlier prompt; day-long sessions need a bound.
)
# Verbatim from ten-levels-of-jev level07/should-compact.ts:19-37.
COMPACT_QUESTIONS = {
    "switched_gears": {
        "type": "noul",
        "instructions": "Is `current_request` a different task from `previous_work`?",
        "criteria": {
            "true": "A new feature, a different file area, a different goal, or an unrelated question",
            "false": "The same task continuing, a follow up, a fix to what was just done",
        },
    },
    "at_boundary": {
        "type": "noul",
        "instructions": "Did `recent_turn` finish a unit of work?",
        "criteria": {
            "true": "Tests passed, a commit was made, a summary was given, or a question was asked of the user",
            "false": "Mid task, more steps clearly remain",
        },
    },
    "needs_history": {
        "type": "score",
        "instructions": "How much of `previous_work` does the next step need?",
        "criteria": [
            "None; the new work stands alone",
            "Some references, a file name or a decision",
            "Most of it; the work continues directly from it",
        ],
    },
    "mid_operation": {
        "type": "noul",
        "instructions": "Is the agent in the middle of a multi step edit whose partial state only exists in the conversation?",
        "criteria": {
            "true": "Half applied changes, a plan being executed step by step, an unfinished refactor",
            "false": "A clean point, nothing half done",
        },
    },
}
NO_HISTORY = "(nothing before this request)"


def lines_from_env() -> dict:
    """JEV_COMPACT_LINES="notice,recommend,request"; anything malformed falls back to the defaults."""
    try:
        notice, recommend, request = (
            int(x) for x in os.environ.get("JEV_COMPACT_LINES", "").split(",")
        )
        if 0 < notice <= recommend <= request:
            return {"notice": notice, "recommend": recommend, "request": request}
    except ValueError:
        pass
    return dict(DEFAULT_LINES)


def trunc(s: str, n: int) -> str:
    return s[: n - 1] + "…" if len(s) > n else s


def build_state(scan: dict, last_assistant) -> dict:
    prompts = scan.get("prompts") or []
    earlier = [trunc(redact(p), 200) for p in prompts[:-1][-PREVIOUS_PROMPTS:]]
    if scan.get("compact_summary"):
        earlier.append("Summary so far: " + trunc(redact(scan["compact_summary"]), 400))
    tools = list(dict.fromkeys(scan.get("tools_after_last_prompt") or []))
    text = (
        last_assistant
        if isinstance(last_assistant, str) and last_assistant.strip()
        else scan.get("last_assistant_text", "")
    )
    return {
        "current_request": trunc(redact(prompts[-1] if prompts else ""), 600),
        "previous_work": "\n".join(earlier) or NO_HISTORY,
        "recent_turn": trunc(redact(text), 600)
        if text.strip()
        else (f"(tool calls only: {', '.join(tools)})" if tools else "(no reply text)"),
        "tools_this_turn": tools,
    }


def decide_tier(
    answers: dict, tokens: int, lines: dict, state: dict
) -> tuple[str, str]:
    if answers["mid_operation"]["noul"] > 0.6:
        return "silent", "mid operation"
    switched = answers["switched_gears"]["noul"] > 0.7
    boundary = (
        answers["at_boundary"]["noul"] > 0.6 and answers["needs_history"]["score"] < 1
    )
    if not switched and not boundary:
        return "silent", "same work continuing"
    reason = (
        f'The task changed from "{trunc(state["previous_work"], 70)}" to "{trunc(state["current_request"], 70)}".'
        if switched
        else "The last turn finished a unit of work and the next step needs little of the earlier context."
    )
    if tokens < lines["recommend"]:
        return "notice", reason
    if tokens < lines["request"]:
        return "recommend", reason
    return "request", reason


def tier_message(tier: str, reason: str, tokens: int, window) -> str | None:
    where = f"{round(tokens / 1000)}k tokens"
    if isinstance(window, int) and window > 0:
        where += f", {tokens / window * 100:.1f}% of the window"
    return {
        "notice": f"Context is at {where}. {reason} Compacting is optional. If you do, run /compact with a short note to yourself.",
        "recommend": f"Recommended: compact now. Context is at {where}. {reason} Run /compact with a short note to yourself, then continue.",
        "request": f"Please compact before continuing. Context is at {where}. {reason} Run /compact with a short note to yourself.",
    }.get(tier)


def ask_jev(state: dict) -> tuple[dict, dict, float]:
    """One Jev call (GC2): (answers, whole response, elapsed seconds)."""
    response = jev_call(state, COMPACT_QUESTIONS, job="compact_advisor")
    return response["answers"], response, response["elapsed"]


def run_hook(host: str, log: Path, user: bool = False) -> None:
    """Stop hook: write one row; print {"systemMessage": ...} only when the tier is not silent. Never raises."""
    row = {
        "host": host,
        "host_model": None,
        "advisor_version": ADVISOR_VERSION,
        "model": os.environ.get("JEV_MODEL") or DEFAULT_MODEL,
        "jev_model": None,
        "ts": time.time(),
        "tier": "silent",
        "answers": None,
        "printed": False,
    }
    try:
        event = json.loads(sys.stdin.read())
        paths = event.get("workspacePaths") or []
        cwd = event.get("cwd") or (paths[0] if paths else os.getcwd())
        if user and project_hooked(repo_root(cwd), host, Path(__file__).name):
            return  # the repo's own Stop hook logs this turn; never log twice
        row.update(
            session_id=event.get("conversationId") or event.get("session_id"),
            cwd=cwd,
            repo=str(repo_root(cwd)),
        )
        transcript = (
            event.get("transcriptPath")
            if host == "agy"
            else event.get("transcript_path")
        )
        if not transcript:
            raise RuntimeError("no transcript")
        scan = scan_transcript(Path(transcript), host)
        if host == "agy" and scan.get("last_response_has_tools"):
            return  # PostInvocation fires before pending tools; this is not a turn boundary.
        tokens, lines = scan.get("tokens", 0), lines_from_env()
        row.update(
            host_model=host_model(event, host, scan),
            tokens=tokens,
            window=scan.get("window"),
            lines=lines,
        )
        if len(scan["prompts"]) < 2:
            row["reason"] = "first request, nothing to move on from"
        elif tokens < lines["notice"]:
            row["reason"] = "below the notice line"
        else:
            state = build_state(scan, event.get("last_assistant_message"))
            answers, response, row["elapsed"] = ask_jev(state)
            row.update(
                jev_model=response.get("model"),
                input_tokens=int(
                    (response.get("usage") or {}).get("input_tokens") or 0
                ),
                answers={
                    k: answers[k].get("noul", answers[k].get("score"))
                    for k in COMPACT_QUESTIONS
                },
            )
            row["tier"], row["reason"] = decide_tier(answers, tokens, lines, state)
            message = tier_message(row["tier"], row["reason"], tokens, row["window"])
            if message:
                output = (
                    {"injectSteps": [{"systemMessage": {"systemMessage": message}}]}
                    if host == "agy"
                    else {"systemMessage": message}
                )
                print(json.dumps(output), flush=True)
                row["printed"] = True
    except Exception as e:
        row["error"] = (
            f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e)
        )
    append_row(log, row)


def main() -> None:
    hook_args = [a for a in sys.argv[2:] if a != "--user"]
    if sys.argv[1:2] == ["hook"] and hook_args in (["claude"], ["codex"], ["agy"]):
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).parent)
        run_hook(
            hook_args[0], log_dir(root) / "compact.jsonl", "--user" in sys.argv[2:]
        )
    # Unknown arguments exit 0 silently; advice must never break the turn.


if __name__ == "__main__":
    main()
