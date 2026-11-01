"""Phase 7 checks: install-check table cells and exit codes on tmp copies of the configs."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import check_install  # noqa: E402
from test_install_user import JEVDEV  # noqa: E402  (checkout copy with bin/ stubs; see there)

FEATURES = [
    "hyper-jev skill",
    "ask-jev skill",
    "bash gate",
    "write gate",
    "compaction advisor",
    "ask_jev_files CLI",
    "bash output pruner",
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
        "jev_patterns.py",
        "redaction.py",
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
    """AC-7.1: wired and trusted tree reads ok except the agy compaction advisor and the pruner (n/a); exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        home = make_home(tmp, root)
        table = check_install.check(root, home, "project")
        assert list(table) == FEATURES, list(table)
        for feature, cells in table.items():
            assert list(cells) == ["claude", "codex", "agy"], cells
            for host, cell in cells.items():
                want = "ok"
                if (feature, host) == ("compaction advisor", "agy") or (
                    feature == "bash output pruner" and host != "claude"
                ):
                    want = "n/a (unavailable)"
                elif feature == "bash output pruner":
                    want = "n/a (user scope only)"
                assert cell == want, (feature, host, cell)
        r = run_cli(root, home)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "| bash gate |" in r.stdout and "ok (unavailable here)" not in r.stdout, (
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


def run_user(home):
    return subprocess.run(
        [sys.executable, str(ROOT / "check_install.py"), "--scope", "user", "--home", str(home)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def user_home(tmp, trusted=False):
    """A tmp home populated by install_user.py; optionally with Codex trust for its three hooks."""
    import install_user

    home = Path(tmp) / "home"
    result = install_user.install(home, JEVDEV)
    if trusted:
        body = "[hooks.state]\n"
        for k in HOOK_KEYS:
            body += f'\n[hooks.state."{home}/.codex/hooks.json:{k}"]\ntrusted_hash = "sha256:abc"\n'
        (home / ".codex/config.toml").write_text(body)
    return home, result["claude_snippet"]


def apply_claude_snippet(home, snippet):
    """What the ClaudeConfig PR does: merge the printed hooks into settings.json and add the two symlinks."""
    hooks = json.loads(snippet[snippet.index("{") : snippet.rindex("}") + 1])
    (home / ".claude").mkdir(exist_ok=True)
    (home / ".claude/settings.json").write_text(json.dumps(hooks))
    (home / ".claude/skills").mkdir()
    for name in ["hyper-jev", "ask-jev"]:
        (home / ".claude/skills" / name).symlink_to(JEVDEV / ".agents/skills" / name)


def check_user_scope():
    """AC-8.4: before the Claude snippet every claude wiring cell is missing; after it, all ok; exit 1 then 0."""
    with tempfile.TemporaryDirectory() as tmp:
        home, snippet = user_home(tmp)
        table = check_install.check(JEVDEV, home, "user")
        assert list(table) == FEATURES, list(table)
        for feature in [
            "hyper-jev skill",
            "ask-jev skill",
            "bash gate",
            "write gate",
            "compaction advisor",
            "bash output pruner",
        ]:
            assert table[feature]["claude"] == "missing", (feature, table[feature])
        assert table["bash output pruner"]["codex"] == "n/a (unavailable)", table
        for feature in ["hyper-jev skill", "ask-jev skill"]:
            assert table[feature]["codex"] == table[feature]["agy"] == "ok", table[feature]
        for feature in ["bash gate", "write gate", "compaction advisor"]:
            assert table[feature]["codex"] == "untrusted", (feature, table[feature])
        assert table["bash gate"]["agy"] == table["write gate"]["agy"] == "ok", table
        assert table["compaction advisor"]["agy"] == "n/a (unavailable)", table
        r = run_user(home)
        assert r.returncode == 1 and r.stdout.startswith("jevdev checkout: "), (r.stdout, r.stderr)

        apply_claude_snippet(home, snippet)
        table = check_install.check(JEVDEV, home, "user")
        assert all(cell == "ok" for row in table.values() for cell in [row["claude"]]), table
        r = run_user(home)
        assert r.returncode == 0, (r.stdout, r.stderr)  # untrusted alone keeps exit 0


def check_pruner_dir_must_hold_the_plugin():
    """The env var alone is not enough: a listed folder without the plugin reads missing."""
    with tempfile.TemporaryDirectory() as tmp:
        home, snippet = user_home(tmp)
        apply_claude_snippet(home, snippet)
        settings = json.loads((home / ".claude/settings.json").read_text())
        assert settings["env"]["CLAUDE_CODE_PLUGIN_DIRS"] == f"{JEVDEV}/pruner", settings["env"]
        settings["env"]["CLAUDE_CODE_PLUGIN_DIRS"] = f"{tmp}/nope/pruner"
        (home / ".claude/settings.json").write_text(json.dumps(settings))
        assert check_install.check(JEVDEV, home, "user")["bash output pruner"]["claude"] == "missing"


def check_pruner_dir_accepts_tilde_and_needs_this_plugin():
    """Claude expands `~` in the var, and only the jev-pruner manifest counts, whatever the folder's name."""
    with tempfile.TemporaryDirectory() as tmp:
        home, snippet = user_home(tmp)
        apply_claude_snippet(home, snippet)
        settings = json.loads((home / ".claude/settings.json").read_text())
        for name, plugin, want in (("pinned", "jev-pruner", "ok"), ("pruner", "other", "missing")):
            manifest = home / name / ".claude-plugin/plugin.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"name": plugin}))
            settings["env"]["CLAUDE_CODE_PLUGIN_DIRS"] = f"~/{name}"
            (home / ".claude/settings.json").write_text(json.dumps(settings))
            cell = check_install.check(JEVDEV, home, "user")["bash output pruner"]["claude"]
            assert cell == want, (name, cell)


def check_user_scope_trusted():
    """Codex trust is keyed on ~/.codex/hooks.json, not the project config path."""
    with tempfile.TemporaryDirectory() as tmp:
        home, snippet = user_home(tmp, trusted=True)
        apply_claude_snippet(home, snippet)
        table = check_install.check(JEVDEV, home, "user")
        want = {"bash gate": "ok", "write gate": "ok", "compaction advisor": "ok"}
        assert {f: table[f]["codex"] for f in want} == want, table
        (home / ".codex/hooks.json").write_text("{nope")
        table = check_install.check(JEVDEV, home, "user")
        assert table["bash gate"]["codex"] == "missing", table
        (home / ".gemini/config/hooks.json").write_text("[]")
        r = run_user(home)
        assert r.returncode == 1 and "Traceback" not in r.stderr, (r.stdout, r.stderr)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_") and callable(fn):
            fn()
            print("ok", name)
    print("all check_install tests passed")
