#!/usr/bin/env python3
"""Report whether each Jev feature is wired in each host (Claude, Codex, agy) at project or user scope.

Read-only: never edits a config and never trusts a Codex hook on the user's behalf.
Exit 1 when any cell is `missing`; `untrusted` alone keeps exit 0.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

HOSTS = ["claude", "codex", "agy"]
FEATURES = [
    "hyper-jev skill",
    "ask-jev skill",
    "bash gate",
    "write gate",
    "compaction advisor",
    "ask_jev_files CLI",
]
CLAUDE_WRITE = ["Write", "Edit", "NotebookEdit"]
AGY_WRITE = ["write_to_file", "replace_file_content", "multi_replace_file_content"]


def load(path, parser):
    """Parsed config or None when the file is absent, unreadable, or malformed."""
    try:
        with open(path, "rb") as f:
            return parser(f)
    except Exception:
        return None


def hook_entries(data, event):
    """(group_index, hook_index, matcher, normalized command) for every hook under `event`."""
    out = []
    groups = data.get("hooks", {}).get(event, []) if isinstance(data, dict) else []
    for i, group in enumerate(groups if isinstance(groups, list) else []):
        if not isinstance(group, dict):
            continue
        hooks = group.get("hooks", [])
        for j, hook in enumerate(hooks if isinstance(hooks, list) else []):
            command = hook.get("command") if isinstance(hook, dict) else None
            if isinstance(command, str):
                out.append(
                    (i, j, str(group.get("matcher", "")), re.sub(r"[\"']", "", command))
                )
    return out


def agy_entries(data, event):
    """Same tuples across every named hook in an agy hooks.json (a map of name -> events)."""
    out = []
    for named in data.values() if isinstance(data, dict) else []:
        out += hook_entries({"hooks": named}, event) if isinstance(named, dict) else []
    return out


def find(entries, matcher_ok, needle):
    """Entries whose matcher passes `matcher_ok` and whose command contains `needle`."""
    return [e for e in entries if matcher_ok(e[2]) and needle in e[3]]


def all_in(names):
    return lambda matcher: all(n in matcher for n in names)


def skill_cells(dirs, name, linked):
    """One cell per host: `dirs` maps host -> skills dir; user scope also requires the entry to be a symlink."""

    def cell(d):
        entry = d / name
        return "ok" if (entry / "SKILL.md").is_file() and (entry.is_symlink() or not linked) else "missing"

    return {h: cell(dirs[h]) for h in HOSTS}


def trusted(state, config, event, i, j):
    return f"{config}:{event}:{i}:{j}" in state


def codex_cell(found, state, config, event):
    if not found:
        return "missing"
    i, j = found[0][:2]
    return "ok" if trusted(state, config, event, i, j) else "untrusted"


def cli_cell(root):
    cli = root / "ask_jev_files.py"
    if not cli.is_file():
        return "missing"
    try:
        ok = (
            subprocess.run(
                [sys.executable, str(cli), "--help"], capture_output=True, timeout=20
            ).returncode
            == 0
        )
    except Exception:
        ok = False
    return "ok" if ok else "missing"


def check(root, home, scope):
    """feature -> host -> cell. Project scope reads the configs under `root`; user scope reads those under `home`.
    Codex trust is read from `home` either way; `root` is also where the ask_jev_files CLI lives."""
    root, home = Path(root), Path(home)
    if scope == "user":
        claude = load(home / ".claude/settings.json", json.load) or {}
        codex_path = home / ".codex/hooks.json"
        codex = load(codex_path, json.load) or {}
        agy = load(home / ".gemini/config/hooks.json", json.load) or {}
        skill_dirs = {
            "claude": home / ".claude/skills",
            "codex": home / ".agents/skills",
            "agy": home / ".gemini/antigravity-cli/skills",
        }
    else:
        claude = load(root / ".claude/settings.json", json.load) or {}
        codex_path = root / ".codex/config.toml"
        codex = load(codex_path, tomllib.load) or {}
        agy = load(root / ".agents/hooks.json", json.load) or {}
        skill_dirs = {
            "claude": root / ".claude/skills",
            "codex": root / ".agents/skills",
            "agy": root / ".agents/skills",
        }
    user = load(home / ".codex/config.toml", tomllib.load)
    state = user.get("hooks", {}).get("state", {}) if isinstance(user, dict) else {}
    state = state if isinstance(state, dict) else {}
    cfg = str(codex_path.absolute())

    pre = lambda d: hook_entries(d, "PreToolUse")
    ok = lambda found: "ok" if found else "missing"
    cli = cli_cell(root)
    table = {
        "hyper-jev skill": skill_cells(skill_dirs, "hyper-jev", scope == "user"),
        "ask-jev skill": skill_cells(skill_dirs, "ask-jev", scope == "user"),
        "bash gate": {
            "claude": ok(find(pre(claude), lambda m: m == "Bash", "scope_sentinel.py")),
            "codex": codex_cell(
                find(pre(codex), lambda m: m == "Bash", "scope_sentinel.py"),
                state,
                cfg,
                "pre_tool_use",
            ),
            "agy": ok(
                find(
                    agy_entries(agy, "PreToolUse"),
                    lambda m: "run_command" in m,
                    "scope_sentinel.py hook agy",
                )
            ),
        },
        "write gate": {
            "claude": ok(find(pre(claude), all_in(CLAUDE_WRITE), "scope_sentinel.py")),
            "codex": codex_cell(
                find(pre(codex), lambda m: m == "apply_patch", "scope_sentinel.py"),
                state,
                cfg,
                "pre_tool_use",
            ),
            "agy": ok(
                find(
                    agy_entries(agy, "PreToolUse"),
                    all_in(AGY_WRITE),
                    "scope_sentinel.py hook agy",
                )
            ),
        },
        "compaction advisor": {
            "claude": ok(
                find(
                    hook_entries(claude, "Stop"),
                    lambda m: True,
                    "compact_advisor.py hook claude",
                )
            ),
            "codex": codex_cell(
                find(
                    hook_entries(codex, "Stop"),
                    lambda m: True,
                    "compact_advisor.py hook codex",
                ),
                state,
                cfg,
                "stop",
            ),
            "agy": "n/a (unavailable)",
        },
        "ask_jev_files CLI": {h: cli for h in HOSTS},
    }
    return table


def render(table):
    lines = ["| Feature | " + " | ".join(HOSTS) + " |", "|---|" + "---|" * len(HOSTS)]
    lines += [
        f"| {f} | " + " | ".join(table[f][h] for h in HOSTS) + " |" for f in FEATURES
    ]
    return "\n".join(lines)


def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Report Jev feature wiring per host.")
    ap.add_argument("--scope", choices=["project", "user"], default="project")
    ap.add_argument("--root", default=str(here))
    ap.add_argument("--home", default=str(Path.home()))
    args = ap.parse_args(argv)
    table = check(Path(args.root), Path(args.home), args.scope)
    if args.scope == "user":
        git = lambda *a: subprocess.run(
            ["git", "-C", args.root, "rev-parse", *a], capture_output=True, text=True
        ).stdout.strip()
        print(f"jevdev checkout: {git('--abbrev-ref', 'HEAD') or '?'} @ {git('--short', 'HEAD') or '?'}")
    print(render(table))
    return (
        1 if any(c == "missing" for row in table.values() for c in row.values()) else 0
    )


if __name__ == "__main__":
    sys.exit(main())
