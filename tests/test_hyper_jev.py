"""Phase 2 checks: hyper-jev skill vendored once, symlinked for Claude, smoke.sh skill wired."""

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).parents[1]
SKILL = ROOT / ".agents/skills/hyper-jev"
LINK = ROOT / ".claude/skills/hyper-jev"
KEYS = re.compile(r"(sk-or-|sk-[A-Za-z0-9_-]{20,}|ghp_|AKIA)")


def test_skill_md_is_vendored_with_name():
    assert "name: hyper-jev" in (SKILL / "SKILL.md").read_text()


def test_license_is_vendored():
    assert "MIT" in (SKILL / "LICENSE").read_text()


def test_claude_link_is_relative_symlink():
    assert LINK.is_symlink()
    assert os.readlink(LINK) == "../../.agents/skills/hyper-jev"
    assert (LINK / "SKILL.md").is_file()


def test_dangling_link_fails_when_agents_copy_removed():
    with tempfile.TemporaryDirectory() as tmp:
        link = Path(tmp) / ".claude/skills/hyper-jev"
        link.parent.mkdir(parents=True)
        link.symlink_to("../../.agents/skills/hyper-jev")
        assert not (link / "SKILL.md").is_file()


def test_no_key_shaped_strings_outside_env_example():
    for path in SKILL.rglob("*"):
        if path.is_file() and path.name != ".env.example":
            assert not KEYS.search(path.read_text(errors="ignore")), path


def test_smoke_codex_skill_prints_interactive_steps():
    out = subprocess.run(
        ["bash", str(ROOT / "smoke.sh"), "codex", "skill"],
        capture_output=True,
        text=True,
    ).stdout
    assert "$hyper-jev" in out and "/skills" in out


def test_readme_has_skills_section():
    text = (ROOT / "README.md").read_text()
    assert "## Skills" in text and "MIT" in text


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok {name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    raise SystemExit(1 if failed else 0)
