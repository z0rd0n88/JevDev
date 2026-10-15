"""Phase 7 checks: install-check table cells and exit codes on tmp copies of the configs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import check_install  # noqa: E402

FEATURES = [
    "hyper-jev skill",
    "ask-jev skill",
    "bash gate",
    "write gate",
    "compaction advisor",
    "ask_jev_files CLI",
]
HOOK_KEYS = ["pre_tool_use:0:0", "pre_tool_use:1:0", "stop:0:0"]


def make_root(tmp):
    """Copy the three configs, the skill files, and the CLI into tmp; skills stay relative symlinks."""
    root = Path(tmp) / "repo"
    for rel in [
        ".claude/settings.json",
        ".codex/config.toml",
        ".agents/hooks.json",
        ".agents/skills/hyper-jev/SKILL.md",
        ".agents/skills/ask-jev/SKILL.md",
        "ask_jev_files.py",
        "scope_sentinel.py",
    ]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    (root / ".claude/skills").mkdir(parents=True)
    for name in ["hyper-jev", "ask-jev"]:
        (root / ".claude/skills" / name).symlink_to(f"../../.agents/skills/{name}")
    return root


def make_home(tmp, root, keys=HOOK_KEYS):
    home = Path(tmp) / "home"
    (home / ".codex").mkdir(parents=True)
    body = "[hooks.state]\n"
    for k in keys:
        body += f'\n[hooks.state."{root}/.codex/config.toml:{k}"]\ntrusted_hash = "sha256:abc"\n'
    (home / ".codex/config.toml").write_text(body)
    return home


def run_cli(root, home):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_install.py"),
            "--root",
            str(root),
            "--home",
            str(home),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def check_all_ok():
    """AC-7.1: wired and trusted tree reads ok except the two documented cells; exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root)
        table = check_install.check(root, home, "project")
        assert list(table) == FEATURES, list(table)
        for feature, cells in table.items():
            assert list(cells) == ["claude", "codex", "agy"], cells
            for host, cell in cells.items():
                want = "ok"
                if (feature, host) == ("write gate", "codex"):
                    want = "ok (unavailable here)"
                if (feature, host) == ("compaction advisor", "agy"):
                    want = "n/a (unavailable)"
                assert cell == want, (feature, host, cell)
        r = run_cli(root, home)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "| bash gate |" in r.stdout and "ok (unavailable here)" in r.stdout, (
            r.stdout
        )


def check_missing_stop():
    """AC-7.2: Codex config without the Stop hook -> codex/compaction missing, exit 1."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root)
        cfg = root / ".codex/config.toml"
        text = cfg.read_text()
        cfg.write_text(text[: text.index("[[hooks.Stop]]")])
        table = check_install.check(root, home, "project")
        assert table["compaction advisor"]["codex"] == "missing", table
        assert table["bash gate"]["codex"] == "ok", table
        assert run_cli(root, home).returncode == 1


def check_agy_array():
    """AC-7.3: hooks.json as a top-level array -> agy hook cells missing, no traceback, exit 1."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root)
        (root / ".agents/hooks.json").write_text("[]")
        table = check_install.check(root, home, "project")
        assert table["bash gate"]["agy"] == "missing", table
        assert table["write gate"]["agy"] == "missing", table
        r = run_cli(root, home)
        assert r.returncode == 1 and "Traceback" not in r.stderr, (r.stdout, r.stderr)


def check_untrusted():
    """AC-7.4: no hooks.state entries -> codex hook cells untrusted, exit stays 0."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root, keys=[])
        table = check_install.check(root, home, "project")
        for feature in ["bash gate", "write gate", "compaction advisor"]:
            assert table[feature]["codex"] == "untrusted", (feature, table[feature])
        assert run_cli(root, home).returncode == 0
        # A missing user config reads the same way.
        (home / ".codex/config.toml").unlink()
        assert (
            check_install.check(root, home, "project")["bash gate"]["codex"]
            == "untrusted"
        )


def check_skills():
    """Dangling skill symlink reads missing without raising; a skill dir without SKILL.md too."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root)
        shutil.rmtree(root / ".agents/skills/hyper-jev")
        table = check_install.check(root, home, "project")
        assert table["hyper-jev skill"] == {
            "claude": "missing",
            "codex": "missing",
            "agy": "missing",
        }, table
        assert table["ask-jev skill"]["claude"] == "ok"


def check_malformed():
    """Malformed TOML/JSON and a missing CLI give missing cells, never a traceback."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root)
        (root / ".codex/config.toml").write_text("not [valid toml")
        (root / ".claude/settings.json").write_text("{nope")
        (root / "ask_jev_files.py").unlink()
        table = check_install.check(root, home, "project")
        assert (
            table["bash gate"]["codex"] == "missing"
            and table["bash gate"]["claude"] == "missing"
        ), table
        assert table["ask_jev_files CLI"] == {
            "claude": "missing",
            "codex": "missing",
            "agy": "missing",
        }, table
        r = run_cli(root, home)
        assert r.returncode == 1 and "Traceback" not in r.stderr


def check_user_scope():
    """--scope user is a clear 'not implemented' until Phase 8, exit 2."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "check_install.py"), "--scope", "user"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2 and "not implemented" in (r.stdout + r.stderr), (
        r.stdout,
        r.stderr,
    )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_") and callable(fn):
            fn()
            print("ok", name)
    print("all check_install tests passed")
