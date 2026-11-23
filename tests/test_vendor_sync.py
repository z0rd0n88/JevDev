"""vendor/workflow-router is an exact copy of my-skills' skills/workflow-router: the copy matches its lock, and sync and check behave on tmp repos."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import vendor_sync  # noqa: E402

SKILL = Path(vendor_sync.SOURCE_PATH)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], check=True, capture_output=True)


def make_source(tmp):
    """A my-skills stand-in: two committed skill files (one executable), one untracked, one outside the skill."""
    src = Path(tmp) / "my-skills"
    (src / SKILL / "hooks").mkdir(parents=True)
    (src / SKILL / "SKILL.md").write_text("name: workflow-router\n")
    (src / SKILL / "hooks/run.py").write_text("print('v1')\n")
    (src / SKILL / "hooks/run.py").chmod(0o755)
    (src / "README.md").write_text("not part of the skill\n")
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "one")
    (src / SKILL / "untracked.txt").write_text("never committed\n")
    return src


def synced(tmp):
    src = make_source(tmp)
    dest, lock = Path(tmp) / "copy", Path(tmp) / "copy.lock.json"
    (src / SKILL / "untracked.txt").unlink()
    vendor_sync.sync(src, dest, lock)
    return src, dest, lock


def test_copy_matches_its_lock():
    """The drift check CI runs: nobody edited, added, removed or re-moded a file under vendor/workflow-router."""
    assert vendor_sync.check() == [], vendor_sync.check()


def test_lock_names_the_source():
    source = vendor_sync.read_lock(vendor_sync.LOCK)["source"]
    assert (source["repo"], source["path"]) == ("z0rd0n88/my-skills", "skills/workflow-router")
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"]) and re.fullmatch(r"[0-9a-f]{40}", source["tree"])


def test_edit_extra_missing_and_mode_are_each_reported():
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "workflow-router"
        shutil.copytree(vendor_sync.DEST, dest)
        assert vendor_sync.check(dest) == []
        (dest / "SKILL.md").write_text("edited here\n")
        (dest / "notes.md").write_text("added here\n")
        (dest / "hooks/questions.json").unlink()
        (dest / "hooks/jev_route.py").chmod(0o644)
        assert vendor_sync.check(dest) == [
            "copy:     changed  SKILL.md",
            "copy:     mode     hooks/jev_route.py 100755 -> 100644",
            "copy:     removed  hooks/questions.json",
            "copy:     added    notes.md",
        ], vendor_sync.check(dest)


def test_sync_copies_committed_skill_files_with_modes():
    with tempfile.TemporaryDirectory() as tmp:
        src = make_source(tmp)
        dest, lock = Path(tmp) / "copy", Path(tmp) / "copy.lock.json"
        try:
            vendor_sync.sync(src, dest, lock)
            raise AssertionError("an untracked file under the skill must stop the sync")
        except vendor_sync.SourceError:
            assert not dest.exists() and not lock.exists()
        (src / SKILL / "untracked.txt").unlink()
        assert vendor_sync.sync(src, dest, lock) == ["added    SKILL.md", "added    hooks/run.py"]
        assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == ["SKILL.md", "hooks/run.py"]
        assert (dest / "hooks/run.py").stat().st_mode & 0o777 == 0o755
        assert (dest / "SKILL.md").stat().st_mode & 0o777 == 0o644
        locked = vendor_sync.read_lock(lock)
        tree = subprocess.run(["git", "-C", str(src), "rev-parse", f"HEAD:{SKILL}"], capture_output=True, text=True).stdout.strip()
        assert locked["source"]["tree"] == tree
        assert vendor_sync.check(dest, lock, src) == []


def test_upstream_change_is_stale_until_resynced():
    with tempfile.TemporaryDirectory() as tmp:
        src, dest, lock = synced(tmp)
        (src / SKILL / "hooks/run.py").write_text("print('v2')\n")
        (src / SKILL / "new.md").write_text("new upstream\n")
        git(src, "rm", "-q", str(SKILL / "SKILL.md"))
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "two")
        assert vendor_sync.check(dest, lock) == []
        assert vendor_sync.check(dest, lock, src) == [
            "upstream: removed  SKILL.md",
            "upstream: changed  hooks/run.py",
            "upstream: added    new.md",
        ], vendor_sync.check(dest, lock, src)
        assert vendor_sync.sync(src, dest, lock) == ["removed  SKILL.md", "changed  hooks/run.py", "added    new.md"]
        assert not (dest / "SKILL.md").exists() and (dest / "new.md").is_file()
        assert vendor_sync.check(dest, lock, src) == []


def test_dirty_source_is_refused_and_copy_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        src, dest, lock = synced(tmp)
        before = lock.read_text()
        (src / SKILL / "SKILL.md").write_text("uncommitted\n")
        for call in (lambda: vendor_sync.sync(src, dest, lock), lambda: vendor_sync.check(dest, lock, src)):
            try:
                call()
                raise AssertionError("a dirty source must raise")
            except vendor_sync.SourceError as exc:
                assert "uncommitted changes" in str(exc)
        assert lock.read_text() == before and (dest / "SKILL.md").read_text() == "name: workflow-router\n"


def test_git_ignored_run_output_is_not_drift_and_survives_sync():
    with tempfile.TemporaryDirectory() as tmp:
        src, _, _ = synced(tmp)
        repo = Path(tmp) / "jevdev"
        dest, lock = repo / "vendor/copy", repo / "vendor/copy.lock.json"
        dest.mkdir(parents=True)
        git(repo, "init", "-q")
        (repo / ".gitignore").write_text("out-*/\n")
        vendor_sync.sync(src, dest, lock)
        out = dest / "hooks/out-run/result.json"
        out.parent.mkdir()
        out.write_text("{}\n")
        assert vendor_sync.check(dest, lock, src) == []
        vendor_sync.sync(src, dest, lock)
        assert out.is_file()


def test_cli_exit_codes():
    run = lambda *args: subprocess.run([sys.executable, str(ROOT / "vendor_sync.py"), *args], capture_output=True, text=True)
    ok = run("check")
    assert ok.returncode == 0 and ok.stdout.startswith("ok: vendor/workflow-router matches the lock"), ok
    with tempfile.TemporaryDirectory() as tmp:
        bad = run("check", "--source", tmp)
        assert bad.returncode == 2 and bad.stderr.startswith("error: "), bad
    assert run("sync").returncode == 2


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
