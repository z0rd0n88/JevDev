#!/usr/bin/env python3
"""Idempotent user-scope installer for the Jev gates, advisor, and skills (Codex and agy).

Writes under --home only: ~/.codex/hooks.json, ~/.gemini/config/hooks.json, four skill symlinks, two ~/.local/bin symlinks, and
~/.local/state/jevdev. The Claude part lives in the ClaudeConfig repo, so it is printed, never applied.
"""

import argparse
import json
import os
from pathlib import Path
import sys

OWNED = ("scope_sentinel.py", "compact_advisor.py")
SKILLS = ("hyper-jev", "ask-jev")
BIN = ("jev", "jev-selfcheck")
LINK_DIRS = (".agents/skills", ".gemini/antigravity-cli/skills")
AGY_WRITE = "write_to_file|replace_file_content|multi_replace_file_content"


class Refused(Exception):
    """The install would clobber or misread something it does not own; nothing was changed."""


def command(jevdev, script, host):
    return (
        f"bash -c 'SCOPE_SENTINEL=1 JEV_LOG_DIR=$HOME/.local/state/jevdev exec bash {jevdev}/with_jev_key.sh "
        f"python3 {jevdev}/{script} hook {host} --user' || true"
    )


def group(cmd, timeout, matcher=None):
    g = {"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]}
    return {"matcher": matcher, **g} if matcher else g


def wanted_codex(jevdev):
    sentinel = command(jevdev, "scope_sentinel.py", "codex")
    return [
        ("PreToolUse", group(sentinel, 10, "Bash")),
        ("PreToolUse", group(sentinel, 10, "apply_patch")),
        ("Stop", group(command(jevdev, "compact_advisor.py", "codex"), 45)),
    ]


def wanted_agy(jevdev):
    sentinel = command(jevdev, "scope_sentinel.py", "agy")
    return {
        "PreToolUse": [
            group(sentinel, 10, "run_command"),
            group(sentinel, 10, AGY_WRITE),
        ]
    }


def owned(g):
    return any(
        isinstance(h, dict) and any(s in str(h.get("command", "")) for s in OWNED)
        for h in g.get("hooks", [])
    )


def merge_codex(data, wanted):
    """data with every owned hook replaced by `wanted`; data itself when its owned groups already match."""
    hooks = data.setdefault("hooks", {})
    have = [(e, g) for e, groups in hooks.items() for g in groups if owned(g)]
    if sorted(map(json.dumps, have)) == sorted(map(json.dumps, wanted)):
        return data
    for event in list(hooks):
        kept = []
        for g in hooks[event]:
            if owned(g):
                g = {
                    **g,
                    "hooks": [
                        h
                        for h in g["hooks"]
                        if not any(s in str(h.get("command", "")) for s in OWNED)
                    ],
                }
            if g.get("hooks"):
                kept.append(g)
        hooks[event] = kept
        if not kept:
            del hooks[event]
    for event, g in wanted:
        hooks.setdefault(event, []).append(g)
    return data


def load_json(path, default):
    if not path.exists():
        return default
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise Refused(f"refusing to edit {path}: not a JSON object")
    return data


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def link_plan(home, jevdev, removing):
    """(link, target, action) per skill and bin link; raises Refused before anything is touched."""
    pairs = [
        (home / d / name, jevdev / ".agents/skills" / name)
        for d in LINK_DIRS
        for name in SKILLS
    ] + [(home / ".local/bin" / name, jevdev / "bin" / name) for name in BIN]
    plan = []
    for link, target in pairs:
        if not removing and not target.exists():
            raise Refused(f"refusing to link to a missing target: {target}")
        if link.is_symlink():
            ours = str(link.readlink()).startswith(str(jevdev))
            action = (
                "remove"
                if removing and ours
                else "keep"
                if removing or link.readlink() == target
                else "relink"
            )
        elif link.exists():
            if not removing:
                kind = "directory" if link.is_dir() else "file"
                raise Refused(f"refusing to replace a real {kind}: {link}")
            action = "keep"
        else:
            action = "keep" if removing else "create"
        plan.append((link, target, action))
    return plan


def claude_snippet(jevdev):
    sentinel, advisor = (command(jevdev, s, "claude") for s in OWNED)
    hooks = {
        "PreToolUse": [
            group(sentinel, 10, "Bash"),
            group(sentinel, 10, "Write|Edit|NotebookEdit"),
        ],
        "Stop": [group(advisor, 45)],
    }
    links = [f"ln -s {jevdev}/.agents/skills/{n} ~/.claude/skills/{n}" for n in SKILLS]
    env = {"CLAUDE_CODE_PLUGIN_DIRS": f"{jevdev}/pruner"}
    return "\n".join(
        [
            "Claude part, not applied (~/.claude is the ClaudeConfig repo): open a PR with no Claude session "
            "running and merge this env and these hooks into ~/.claude/settings.json:",
            json.dumps({"env": env, "hooks": hooks}, indent=2),
            "then run:",
            *links,
        ]
    )


def removal_snippet():
    return (
        "Claude part, not applied: in a ClaudeConfig PR with no Claude session running, delete the hook entries "
        "whose command contains scope_sentinel.py or compact_advisor.py and env.CLAUDE_CODE_PLUGIN_DIRS's pruner "
        "entry from ~/.claude/settings.json, then run:\n"
        "rm " + " ".join(f"~/.claude/skills/{n}" for n in SKILLS)
    )


def apply(home, jevdev, removing):
    home, jevdev = Path(home), Path(jevdev)
    codex_path, agy_path = (
        home / ".codex/hooks.json",
        home / ".gemini/config/hooks.json",
    )
    codex, agy = (
        load_json(codex_path, {"hooks": {}}),
        load_json(agy_path, {}),
    )  # preflight: nothing written yet
    plan = link_plan(home, jevdev, removing)
    old_codex, old_agy = json.dumps(codex), json.dumps(agy)
    codex = merge_codex(codex, [] if removing else wanted_codex(jevdev))
    if removing:
        agy.pop("jevdev", None)
    else:
        agy["jevdev"] = wanted_agy(jevdev)

    changed = []
    for path, data, old in ((codex_path, codex, old_codex), (agy_path, agy, old_agy)):
        if json.dumps(data) != old:
            write_json(path, data)
            changed.append(str(path))
    for link, target, action in plan:
        if action == "keep":
            continue
        if action == "remove":
            link.unlink()
        else:
            link.parent.mkdir(parents=True, exist_ok=True)
            if action == "relink":
                link.unlink()
            link.symlink_to(target)
        changed.append(str(link))
    state = home / ".local/state/jevdev"
    if not removing and not state.exists():
        state.mkdir(mode=0o700, parents=True)
        changed.append(str(state))
    return {
        "changed": changed,
        "claude_snippet": removal_snippet() if removing else claude_snippet(jevdev),
    }


def install(home, jevdev):
    return apply(home, jevdev, removing=False)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Install the Jev gates, advisor, and skills at user scope."
    )
    ap.add_argument("--home", default=os.environ.get("HOME") or str(Path.home()))
    ap.add_argument("--jevdev", default="/home/alex/JevDev")
    ap.add_argument(
        "--remove", action="store_true", help="delete what this installer owns"
    )
    args = ap.parse_args(argv)
    try:
        result = apply(args.home, args.jevdev, args.remove)
    except (Refused, OSError, ValueError) as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(
        "\n".join(["changed:", *(f"  {p}" for p in result["changed"])])
        if result["changed"]
        else "nothing to change"
    )
    print(result["claude_snippet"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
