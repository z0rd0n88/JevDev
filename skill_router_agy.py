#!/usr/bin/env python3
"""Antigravity (agy) wrapper for the Jev two-request skill router.

Leaves skill_router.py (Claude Code + Codex) untouched and adds Antigravity
skill discovery (~/.gemini/config and ~/.gemini/antigravity-cli) plus
Antigravity's PreInvocation ephemeralMessage hook contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_router import inspect_roster, skill_entry, suggest  # noqa: E402


def agy_roster() -> list[dict]:
    """Read Antigravity skills from ~/.gemini/config and ~/.gemini/antigravity-cli."""
    gemini_home = Path(os.environ.get("GEMINI_HOME") or Path.home() / ".gemini")
    roots = (
        gemini_home / "config/skills",
        gemini_home / "antigravity-cli/skills",
        gemini_home / "antigravity-cli/builtin/skills",
    )
    entries: dict[str, dict] = {}
    for root in roots:
        for path in sorted(root.glob("*/SKILL.md")):
            try:
                entries.setdefault(
                    path.parent.name, skill_entry(path.parent.name, path)
                )
            except Exception:
                continue
    for path in sorted((gemini_home / "config/plugins").glob("*/skills/*/SKILL.md")):
        try:
            entries.setdefault(path.parent.name, skill_entry(path.parent.name, path))
        except Exception:
            continue
    if not entries:
        raise RuntimeError("Antigravity skill listing was empty")
    return list(entries.values())


def _already_routed(event: dict, prompt: str) -> bool:
    """Skip mid-turn tool continuations (invocationNum > 1) and duplicate hook runs."""
    inv_num = event.get("invocationNum")
    if isinstance(inv_num, int) and inv_num > 1:
        return True
    conv_id = str(event.get("conversationId") or "")
    if not conv_id:
        return False
    digest = hashlib.sha256(f"{conv_id}:{prompt}".encode("utf-8")).hexdigest()[:20]
    state_dir = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "agy-jev-router"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        marker = state_dir / digest
        if marker.exists():
            return True
        marker.write_text("1", encoding="utf-8")
    except Exception:
        pass
    return False


def run_prompt_hook() -> None:
    """Route an Antigravity PreInvocation event and return an ephemeralMessage hint."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        prompt = (
            (event.get("lastUserInput") or event.get("prompt"))
            if isinstance(event, dict)
            else None
        )
        if not isinstance(prompt, str) or not prompt.strip():
            print("{}")
            return
        if isinstance(event, dict) and _already_routed(event, prompt):
            print("{}")
            return
        routing = suggest(prompt, agy_roster())
        suggestion = routing.get("suggestion")
        if not suggestion:
            print("{}")
            return
        context = (
            f"Jev skill router suggests `{suggestion}` for this request. "
            "Load that skill and use its instructions if it fits the task."
        )
        print(json.dumps({"injectSteps": [{"ephemeralMessage": context}]}))
    except Exception:
        # Fail-open: never block an Antigravity PreInvocation turn.
        print("{}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("agy",), default="agy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("measure")
    route = sub.add_parser("route")
    route.add_argument("request")
    sub.add_parser("hook", help="handle an Antigravity PreInvocation event from stdin")
    args = parser.parse_args()
    if args.command == "hook":
        run_prompt_hook()
        return
    entries = agy_roster()
    if args.command == "measure":
        print(json.dumps(inspect_roster(entries), indent=2, sort_keys=True))
    elif args.command == "route":
        print(json.dumps(suggest(args.request, entries), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, KeyError) as error:
        print(f"skill_router_agy: {error}", file=sys.stderr)
        sys.exit(2)
