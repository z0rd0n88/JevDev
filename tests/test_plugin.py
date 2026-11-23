"""The jev plugin: manifest paths resolve, hooks stay off by default, and an enabled hook runs the right script."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / ".claude-plugin/plugin.json"
GATE = ROOT / "plugin/jev-hook.sh"
SCRIPTS = {
    "router": ["skill_router.py", "--host", "claude", "hook"],
    "sentinel": ["scope_sentinel.py", "hook", "claude", "--user"],
    "advisor": ["compact_advisor.py", "hook", "claude", "--user"],
}
# Stands in for python3 so an enabled hook shows what it would run, with no Jev call.
FAKE_PYTHON = '#!/bin/sh\nprintf "%s\\n" "$@"\nprintf "SCOPE_SENTINEL=%s\\n" "$SCOPE_SENTINEL"\ncat >/dev/null\n'


def manifest():
    return json.loads(MANIFEST.read_text())


def run_gate(name, tmp, **env_extra):
    fake = Path(tmp) / "fakebin"
    fake.mkdir(exist_ok=True)
    (fake / "python3").write_text(FAKE_PYTHON)
    (fake / "python3").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ("JEV_HOOKS", "CLAUDE_PROJECT_DIR")}
    env.update(PATH=f"{fake}{os.pathsep}{env['PATH']}", HOME=tmp, **env_extra)
    return subprocess.run(["bash", str(GATE), name], input="{}", env=env, capture_output=True, text=True, timeout=30)


def test_manifest_paths_exist():
    m = manifest()
    assert m["name"] == "jev"
    for rel in m["skills"]:
        assert (ROOT / rel).is_dir(), rel
    assert (ROOT / m["hooks"]).is_file()
    for skill in ("ask-jev", "hyper-jev"):
        assert (ROOT / ".agents/skills" / skill / "SKILL.md").is_file(), skill


def test_hook_commands_go_through_the_gate():
    hooks = json.loads((ROOT / manifest()["hooks"]).read_text())["hooks"]
    commands = [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]
    assert len(commands) == 4
    for c in commands:
        assert c.startswith('bash "${CLAUDE_PLUGIN_ROOT}/plugin/jev-hook.sh" '), c
        assert c.split()[2] in SCRIPTS, c


def test_bin_scripts_are_executable():
    for name in ("jev", "ask-jev-files"):
        assert os.access(ROOT / "bin" / name, os.X_OK), name
    assert os.access(GATE, os.X_OK)


def test_hooks_are_off_without_jev_hooks():
    with tempfile.TemporaryDirectory() as tmp:
        for name in SCRIPTS:
            proc = run_gate(name, tmp)
            assert proc.returncode == 0 and proc.stdout == "", (name, proc.stdout, proc.stderr)
            proc = run_gate(name, tmp, JEV_HOOKS="something-else")
            assert proc.returncode == 0 and proc.stdout == "", (name, proc.stdout)


def test_enabled_hook_runs_its_script():
    with tempfile.TemporaryDirectory() as tmp:
        for name, cmd in SCRIPTS.items():
            for flag in ("1", "all", name, f"x,{name}"):
                proc = run_gate(name, tmp, JEV_HOOKS=flag)
                assert proc.returncode == 0, (name, flag, proc.stderr)
                lines = proc.stdout.splitlines()
                assert lines[0] == str(ROOT / cmd[0]) and lines[1:-1] == cmd[1:], (name, flag, lines)
                assert lines[-1] == "SCOPE_SENTINEL=1"


def test_project_copy_wins_over_plugin_copy():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "proj"
        (project / ".claude").mkdir(parents=True)
        (project / ".claude/settings.json").write_text('{"hooks": "python3 scope_sentinel.py hook"}')
        proc = run_gate("sentinel", tmp, JEV_HOOKS="1", CLAUDE_PROJECT_DIR=str(project))
        assert proc.returncode == 0 and proc.stdout == "", proc.stdout
        proc = run_gate("advisor", tmp, JEV_HOOKS="1", CLAUDE_PROJECT_DIR=str(project))
        assert proc.stdout.startswith(str(ROOT / "compact_advisor.py")), proc.stdout


def test_unknown_hook_is_a_usage_error():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_gate("nope", tmp, JEV_HOOKS="1")
        assert proc.returncode == 64 and "unknown hook" in proc.stderr


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
