"""Phase 8 checks: install_user.py against a tmp --home (never the real one)."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install_user.py"
OTHER = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo other"}]}]}}
SKILL_LINKS = [
    ".agents/skills/hyper-jev",
    ".agents/skills/ask-jev",
    ".gemini/antigravity-cli/skills/hyper-jev",
    ".gemini/antigravity-cli/skills/ask-jev",
]


def run(home, *flags):
    return subprocess.run(
        [
            sys.executable,
            str(INSTALLER),
            "--home",
            str(home),
            "--jevdev",
            str(ROOT),
            *flags,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def snapshot(home):
    """Every file's bytes and every symlink's target under home, for byte-identical comparisons."""
    out = {}
    for p in sorted(Path(home).rglob("*")):
        rel = str(p.relative_to(home))
        out[rel] = (
            ("link", str(p.readlink()))
            if p.is_symlink()
            else ("dir",)
            if p.is_dir()
            else ("file", p.read_bytes())
        )
    return out


def make_home(tmp):
    home = Path(tmp) / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex/hooks.json").write_text(json.dumps(OTHER))
    return home


def check_install_twice():
    """AC-8.1: exact Codex and agy entries, four symlinks, Claude snippet; second run changes nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        home = make_home(tmp)
        first = run(home)
        assert first.returncode == 0, (first.stdout, first.stderr)

        hooks = json.loads((home / ".codex/hooks.json").read_text())["hooks"]
        assert "UserPromptSubmit" in hooks, "the installer must include Codex routing"
        assert hooks["Stop"][0] == OTHER["hooks"]["Stop"][0], (
            "existing entry must be preserved"
        )
        pre = hooks["PreToolUse"]
        assert [g["matcher"] for g in pre] == ["Bash", "apply_patch"], pre
        for g in pre:
            [h] = g["hooks"]
            assert h["timeout"] == 10 and h["command"].endswith("|| true"), h
            assert f"{ROOT}/scope_sentinel.py hook codex --user" in h["command"], h
            assert "JEV_LOG_DIR=$HOME/.local/state/jevdev" in h["command"], h
            assert f"{ROOT}/with_jev_key.sh" in h["command"], h
        assert len(hooks["Stop"]) == 2, hooks["Stop"]
        [stop] = hooks["Stop"][1]["hooks"]
        assert (
            f"{ROOT}/compact_advisor.py hook codex --user" in stop["command"]
            and stop["timeout"] == 45
        ), stop
        assert "JEV_LOG_DIR=" in stop["command"], stop

        agy = json.loads((home / ".gemini/config/hooks.json").read_text())
        assert list(agy) == ["jevdev"] and set(agy["jevdev"]) == {
            "PreToolUse",
            "PreInvocation",
            "PostInvocation",
        }, agy
        assert (
            "--host agy hook --user" in agy["jevdev"]["PreInvocation"][0]["command"]
        ), agy
        assert (
            "compact_advisor.py hook agy --user"
            in agy["jevdev"]["PostInvocation"][0]["command"]
        ), agy
        matchers = [g["matcher"] for g in agy["jevdev"]["PreToolUse"]]
        assert matchers == [
            "run_command",
            "write_to_file|replace_file_content|multi_replace_file_content",
        ], matchers
        for g in agy["jevdev"]["PreToolUse"]:
            assert (
                f"{ROOT}/scope_sentinel.py hook agy --user" in g["hooks"][0]["command"]
            ), g

        for link in SKILL_LINKS:
            assert (home / link).is_symlink() and (
                home / link / "SKILL.md"
            ).is_file(), link
        assert oct((home / ".local/state/jevdev").stat().st_mode & 0o777) == "0o700"

        out = first.stdout
        assert (
            out.count("ln -s") == 2
            and "~/.claude/skills/hyper-jev" in out
            and "~/.claude/skills/ask-jev" in out
        ), out
        claude = json.loads(out[out.index("{") : out.rindex("}") + 1])["hooks"]
        assert [g.get("matcher") for g in claude["PreToolUse"]] == [
            "Bash",
            "Write|Edit|NotebookEdit",
        ], claude
        commands = [
            h["command"]
            for g in claude["PreToolUse"] + claude["Stop"] + claude["UserPromptSubmit"]
            for h in g["hooks"]
        ]
        assert len(commands) == 4 and all(
            ("hook claude --user" in c or "--host claude hook --user" in c)
            and c.endswith("|| true")
            for c in commands
        ), commands
        assert "nothing to change" not in out

        before = snapshot(home)
        second = run(home)
        assert second.returncode == 0 and "nothing to change" in second.stdout, (
            second.stdout,
            second.stderr,
        )
        assert snapshot(home) == before, (
            "second run must leave every file byte-identical"
        )


def check_refuses_real_directory():
    """AC-8.3 negative: a real skill directory is never replaced; exit 2, JSON error, nothing changed."""
    with tempfile.TemporaryDirectory() as tmp:
        home = make_home(tmp)
        real = home / ".agents/skills/hyper-jev"
        real.mkdir(parents=True)
        (real / "SKILL.md").write_text("mine")
        before = snapshot(home)
        r = run(home)
        assert r.returncode == 2, (r.stdout, r.stderr)
        assert json.loads(r.stdout) == {
            "error": f"refusing to replace a real directory: {real}"
        }, r.stdout
        assert snapshot(home) == before, "a refusal must change nothing"


def check_replaces_stale_symlink():
    """A symlink pointing elsewhere is repointed; a malformed hooks.json is refused untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        home = make_home(tmp)
        link = home / ".agents/skills/ask-jev"
        link.parent.mkdir(parents=True)
        link.symlink_to(tmp)
        assert run(home).returncode == 0
        assert link.readlink() == ROOT / ".agents/skills/ask-jev"

        (home / ".codex/hooks.json").write_text("{nope")
        before = snapshot(home)
        r = run(home)
        assert r.returncode == 2 and "error" in json.loads(r.stdout), (
            r.stdout,
            r.stderr,
        )
        assert snapshot(home) == before


def check_remove():
    """--remove deletes only what the installer owns and prints the Claude removal snippet."""
    with tempfile.TemporaryDirectory() as tmp:
        home = make_home(tmp)
        agy_other = home / ".gemini/config/hooks.json"
        agy_other.parent.mkdir(parents=True)
        agy_other.write_text(json.dumps({"mine": {"Stop": []}}))
        foreign = home / ".agents/skills/foreign"
        foreign.parent.mkdir(parents=True)
        foreign.symlink_to(tmp)
        assert run(home).returncode == 0
        r = run(home, "--remove")
        assert r.returncode == 0 and "~/.claude/skills/hyper-jev" in r.stdout, (
            r.stdout,
            r.stderr,
        )
        assert json.loads((home / ".codex/hooks.json").read_text()) == OTHER
        assert json.loads(agy_other.read_text()) == {"mine": {"Stop": []}}
        assert [link for link in SKILL_LINKS if (home / link).is_symlink()] == []
        assert foreign.is_symlink(), "a symlink the installer does not own must stay"
        again = run(home, "--remove")
        assert again.returncode == 0 and "nothing to change" in again.stdout, (
            again.stdout
        )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_") and callable(fn):
            fn()
            print("ok", name)
    print("all install_user tests passed")
