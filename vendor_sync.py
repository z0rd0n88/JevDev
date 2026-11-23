#!/usr/bin/env python3
"""Keep vendor/workflow-router/ an exact copy of skills/workflow-router/ in z0rd0n88/my-skills.

  vendor_sync.py check                 the copy matches vendor/workflow-router.lock.json (offline)
  vendor_sync.py check --source DIR    ...and the lock matches a my-skills checkout at DIR
  vendor_sync.py sync  --source DIR    replace the copy from a my-skills checkout and rewrite the lock

my-skills is the only place the skill is edited. The lock records every file's sha256 and mode, so a
hand edit here fails `check` (and CI, through tests/test_vendor_sync.py), and an upstream change
fails `check --source`. Exit: 0 in sync, 1 drift, 2 the source checkout cannot be used.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SOURCE_REPO = "z0rd0n88/my-skills"
SOURCE_PATH = "skills/workflow-router"
DEST = ROOT / "vendor" / "workflow-router"
LOCK = ROOT / "vendor" / "workflow-router.lock.json"


class SourceError(Exception):
    """The my-skills checkout is missing, dirty, or holds something this script will not copy."""


def _git(source: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise SourceError(f"git {' '.join(args)} failed in {source}: {p.stderr.strip()[:200]}")
    return p.stdout


def _entry(path: Path, mode: str) -> dict[str, str]:
    return {"mode": mode, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _ignored(dest: Path) -> set[str]:
    """Files under the copy that git ignores, such as the judges' out-*/ run output. Empty outside a git checkout."""
    p = subprocess.run(
        ["git", "-C", str(dest), "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        capture_output=True,
        text=True,
    )
    return set(p.stdout.split("\0")) - {""} if p.returncode == 0 else set()


def copy_files(dest: Path) -> dict[str, dict[str, str]]:
    """Every file under the copy that git does not ignore, keyed by its path inside it. The mode is git's."""
    if not dest.is_dir():
        return {}
    ignored = _ignored(dest)
    files = {}
    for path in sorted(dest.rglob("*")):
        rel = path.relative_to(dest).as_posix()
        if rel in ignored:
            continue
        if path.is_symlink():
            files[rel] = {"mode": "120000", "sha256": ""}
        elif path.is_file():
            files[rel] = _entry(path, "100755" if path.stat().st_mode & 0o100 else "100644")
    return files


def source_files(source: Path) -> dict[str, dict[str, str]]:
    """The committed files under SOURCE_PATH. Refuses a dirty checkout, so the lock always names real commits."""
    if _git(source, "status", "--porcelain", "--", SOURCE_PATH).strip():
        raise SourceError(f"{source} has uncommitted changes under {SOURCE_PATH}; commit or stash them first")
    files = {}
    for line in _git(source, "ls-files", "-s", "-z", "--", SOURCE_PATH).split("\0"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        mode = meta.split()[0]
        if mode not in ("100644", "100755"):
            raise SourceError(f"{path} has mode {mode}; only regular files are copied")
        files[path[len(SOURCE_PATH) + 1 :]] = _entry(source / path, mode)
    if not files:
        raise SourceError(f"{source} has no committed files under {SOURCE_PATH}")
    return files


def source_ids(source: Path) -> dict[str, str]:
    """Where the files came from: the last commit that touched the skill, and its git tree id at HEAD."""
    return {
        "repo": SOURCE_REPO,
        "path": SOURCE_PATH,
        "commit": _git(source, "log", "-1", "--format=%H", "--", SOURCE_PATH).strip(),
        "tree": _git(source, "rev-parse", f"HEAD:{SOURCE_PATH}").strip(),
    }


def diff(new: dict[str, dict[str, str]], old: dict[str, dict[str, str]]) -> list[str]:
    """One line per file that differs between two file maps, worded as what `new` did to `old`."""
    lines = []
    for path in sorted(new.keys() | old.keys()):
        if path not in old:
            lines.append(f"added    {path}")
        elif path not in new:
            lines.append(f"removed  {path}")
        elif new[path]["sha256"] != old[path]["sha256"]:
            lines.append(f"changed  {path}")
        elif new[path]["mode"] != old[path]["mode"]:
            lines.append(f"mode     {path} {old[path]['mode']} -> {new[path]['mode']}")
    return lines


def read_lock(lock: Path) -> dict:
    return json.loads(lock.read_text())


def check(dest: Path = DEST, lock: Path = LOCK, source: Path | None = None) -> list[str]:
    """Problems found, each a printable line. Empty means in sync."""
    locked = read_lock(lock)
    problems = [f"copy:     {line}" for line in diff(copy_files(dest), locked["files"])]
    if source is not None:
        problems += [f"upstream: {line}" for line in diff(source_files(source), locked["files"])]
    return problems


def sync(source: Path, dest: Path = DEST, lock: Path = LOCK) -> list[str]:
    """Replace the copy with the source's committed files and rewrite the lock. Returns what changed."""
    files = source_files(source)
    ids = source_ids(source)
    before = copy_files(dest)
    for rel in before:  # ignored run output stays where it is
        (dest / rel).unlink()
    for rel, entry in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / SOURCE_PATH / rel, target)
        target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
    lock.write_text(json.dumps({"source": ids, "files": files}, indent=2, sort_keys=True) + "\n")
    return diff(files, before)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["check", "sync"])
    parser.add_argument("--source", type=Path, help="a my-skills checkout")
    args = parser.parse_args(argv)
    try:
        if args.mode == "sync":
            if args.source is None:
                parser.error("sync needs --source")
            changed = sync(args.source)
            ids = read_lock(LOCK)["source"]
            print("\n".join(changed) if changed else "no file changed")
            print(f"synced {DEST.relative_to(ROOT)} to {SOURCE_REPO}@{ids['commit'][:12]} (tree {ids['tree'][:12]})")
            return 0
        problems = check(source=args.source)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if problems:
        print("\n".join(problems))
        print(
            f"\n{DEST.relative_to(ROOT)} is out of sync. Edit the skill in {SOURCE_REPO} ({SOURCE_PATH}), never here, "
            "then run: python3 vendor_sync.py sync --source <my-skills checkout>",
            file=sys.stderr,
        )
        return 1
    ids = read_lock(LOCK)["source"]
    against = "the lock and the source checkout" if args.source else "the lock"
    print(f"ok: {DEST.relative_to(ROOT)} matches {against} ({SOURCE_REPO}@{ids['commit'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
