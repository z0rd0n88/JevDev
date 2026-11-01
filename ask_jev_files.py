#!/usr/bin/env python3
"""Ask Jev typed questions about files, a command's output, or your own state, from any repo.

  ask_jev_files.py files [-r] -q QUESTIONS_JSON PATH_OR_GLOB...
  ask_jev_files.py pick  -q QUESTION_TEXT PATH...
  ask_jev_files.py ask   -q QUESTIONS_JSON [--state TEXT] [--paths P...] [--command CMD]

JSON on stdout. Exit codes: 0 ok; 2 refused or failed ({"error": ...}); 64 usage; 78 no Jev key.
Whole files only, no chunking. "The repo" is the git toplevel of the process cwd.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import glob
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from jev_patterns import JevError, NO_KEY, call, has_key, model_name
from scope_sentinel import (
    BASH_QUESTIONS,
    BLOCK_NOTICE,
    SENTINEL_VERSION,
    append_row,
    command_view,
    gate_bash,
    is_risky,
    redact,
    repo_root,
)

SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".sessions",
        "dist",
        "build",
        "coverage",
        ".pi",
        ".local",
        "__pycache__",
    }
)
MAX_FILE_CHARS = 240000
MAX_FILES = 255
MAX_ASK_FILES = 20
STATE_TOKEN_BUDGET = 60000
MAX_OWN_STATE_CHARS = 8000
PICK_FLOOR = 0.3
WORKERS = 16
BINARY_NAME = re.compile(
    r"\.(png|jpe?g|gif|webp|ico|pdf|zip|gz|tgz|woff2?|ttf|mp[34]|mov|lock)$", re.I
)


def expand(patterns: list[str], root: Path, recursive: bool) -> list[str]:
    """Absolute paths for patterns anchored at root. A glob keeps its hits; a literal directory becomes
    dir/* (dir/**/* with recursive), so dotfiles are left out as upstream does."""
    found = []
    for pattern in patterns:
        if any(c in pattern for c in "*?[]"):
            hits = glob.glob(pattern, root_dir=root, recursive=True)
        elif os.path.isdir(os.path.join(root, pattern)):
            hits = glob.glob(
                os.path.join(pattern, "**/*" if recursive else "*"),
                root_dir=root,
                recursive=True,
            )
        else:
            hits = [pattern]
        found += [os.path.join(root, hit) for hit in hits]
    return list(dict.fromkeys(found))


def prune(
    paths: list[str], root: Path, cap: int = MAX_FILES
) -> tuple[list[str], list[dict]]:
    """Split paths into repo-relative files worth reading and {"path", "reason"} skips."""
    kept, skipped = [], []
    real_root = root.resolve()
    for raw in paths:
        full = Path(raw) if os.path.isabs(raw) else root / raw
        try:
            rel = full.resolve().relative_to(real_root).as_posix()
        except ValueError:
            skipped.append({"path": raw, "reason": "outside the repo"})
            continue
        if rel in kept:
            continue
        reason = None
        if full.is_dir():
            continue  # a glob hit on a directory (node_modules itself) is not a file to report
        if SKIP_DIRS & set(rel.split("/")):
            reason = "skipped directory"
        elif not full.exists():
            reason = "not found"
        elif full.stat().st_size == 0:
            reason = "empty"
        elif full.stat().st_size > MAX_FILE_CHARS:
            reason = f"too large, {full.stat().st_size} bytes"
        elif BINARY_NAME.search(rel):
            reason = "binary or lock file"
        elif len(kept) >= cap:
            reason = f"over the {cap} file cap; narrow the pattern"
        if reason:
            skipped.append({"path": rel, "reason": reason})
        else:
            kept.append(rel)
    return kept, skipped


def read_state(rel: str, root: Path) -> dict:
    data = (root / rel).read_bytes()
    if b"\0" in data[:8192]:
        raise ValueError("binary")
    return {"path": rel, "content": redact(data.decode("utf-8", errors="replace"))}


def validate_questions(obj) -> dict:
    if not isinstance(obj, dict) or not obj:
        raise ValueError("expected a non-empty JSON object of questions")
    for qid, q in obj.items():
        if not isinstance(q, dict) or q.get("type") not in ("noul", "choice", "score"):
            raise ValueError(f"{qid}: type must be noul, choice, or score")
        if not isinstance(q.get("instructions"), str):
            raise ValueError(f"{qid}: instructions must be a string")
        criteria = q.get("criteria")
        if q["type"] == "choice" and not (
            isinstance(criteria, dict) and 1 <= len(criteria) <= 255
        ):
            raise ValueError(
                f"{qid}: choice needs a criteria object with 1 to 255 keys"
            )
        if q["type"] == "score" and not (
            isinstance(criteria, list)
            and 2 <= len(criteria) <= 10
            and all(isinstance(c, str) for c in criteria)
        ):
            raise ValueError(f"{qid}: score needs a criteria list of 2 to 10 strings")
    return obj


def parse_questions(text: str) -> dict:
    try:
        return validate_questions(json.loads(text))
    except ValueError as e:
        raise ValueError(f"invalid questions_json: {e}") from None


def split_parts(parts: dict[str, int], budget: int) -> list[list[str]]:
    """Greedy largest-first first-fit packing of part names into bins of at most budget tokens."""
    bins = []
    for name in sorted(parts, key=lambda n: -parts[n]):
        for b in bins:
            if b[1] + parts[name] <= budget:
                b[0].append(name)
                b[1] += parts[name]
                break
        else:
            bins.append([[name], parts[name]])
    return [names for names, _ in bins]


def emit(obj: dict, code: int = 0) -> int:
    print(json.dumps(obj))
    return code


def redact_deep(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_deep(v) for k, v in value.items()}
    return value


def tokens(part) -> int:
    return math.ceil(len(json.dumps(part)) / 4)


def cmd_files(args) -> int:
    try:
        questions = parse_questions(args.q)
    except ValueError as e:
        return emit({"error": str(e)}, 2)
    if not has_key():
        return emit({"error": NO_KEY}, 78)
    cwd = Path(os.getcwd())
    root = repo_root(str(cwd))
    kept, skipped = prune(expand(args.paths, cwd, args.recursive), root)
    model = model_name(args.model)

    def one(rel):
        try:
            state = read_state(rel, root)
        except ValueError as e:
            return rel, None, str(e), False
        except OSError as e:
            return rel, None, f"unreadable: {e.strerror}", False
        try:
            return (
                rel,
                call(state, questions, job="ask_jev_files", model=model),
                None,
                True,
            )
        except JevError as e:
            return rel, None, f"jev: {redact(e.stderr) or e}", True

    results, calls, jev_model = [], 0, None
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for rel, response, reason, called in pool.map(one, kept):
            calls += called
            if reason:
                skipped.append({"path": rel, "reason": reason})
            else:
                results.append({"path": rel, "answers": response["answers"]})
                jev_model = jev_model or response.get("model")
    results.sort(key=lambda r: r["path"])
    return emit(
        {"results": results, "skipped": skipped, "calls": calls, "model": jev_model}
    )


def cmd_pick(args) -> int:
    root = repo_root(os.getcwd())
    kept, skipped = prune([os.path.abspath(p) for p in args.paths], root)
    skipped += [{"path": p, "reason": "over the 254 candidate cap"} for p in kept[254:]]
    kept = kept[:254]
    if not kept:
        return emit(
            {"path": None, "confidence": 0, "probabilities": {}, "skipped": skipped}
        )
    if not has_key():
        return emit({"error": NO_KEY}, 78)
    questions = {
        "pick": {
            "type": "choice",
            "instructions": args.q,
            "criteria": {
                **{rel: None for rel in kept},
                "none": "No file in the list fits",
            },
        }
    }
    try:
        answer = call(
            {"question": args.q, "files": kept},
            questions,
            job="ask_jev_pick",
            model=model_name(args.model),
        )["answers"]["pick"]
    except (RuntimeError, KeyError) as e:
        return emit(
            {"error": f"pick failed: {redact(getattr(e, 'stderr', '')) or e}"}, 2
        )
    choice, confidence = answer["choice"], answer["confidence"]
    path = None if choice == "none" or confidence < PICK_FLOOR else choice
    return emit(
        {
            "path": path,
            "confidence": confidence,
            "probabilities": answer.get("probabilities", {}),
            "skipped": skipped,
        }
    )


def parse_own_state(text: str) -> dict:
    if text.lstrip()[:1] in ("{", "["):
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
    return {"text": text}


def gate_command(command: str, cwd: Path, root: Path, model: str):
    """Judge command live and log the decision. Returns (blocked, reason); raises RuntimeError or KeyError."""
    view, hits, unreliable = command_view(command)
    log_dir = (
        Path(os.environ["JEV_LOG_DIR"])
        if os.environ.get("JEV_LOG_DIR")
        else root / ".local"
    )
    answers, response = None, {}
    if len(view) > 2000:
        blocked, reason = True, f"the judge reads 2000 characters and this command has {len(view)}"
    else:
        response = call(
            {"command": view, "cwd": str(root)},
            BASH_QUESTIONS,
            job="ask_jev_gate",
            model=model,
        )
        answers = response["answers"]
        blocked, reason = gate_bash(answers)
    append_row(
        log_dir / "sentinel.jsonl",
        {
            "host": "cli",
            "host_model": None,
            "sentinel_version": SENTINEL_VERSION,
            "model": model,
            "ts": time.time(),
            "session_id": None,
            "source": "ask_jev_files",
            "gate": "bash",
            "cwd": str(cwd),
            "repo": str(root),
            "command": view[:2000],
            "risky": is_risky(command),
            "redacted_hits": hits,
            "scan_unreliable": unreliable,
            "clipped": len(view) > 2000,
            "effect": answers["effect"]["choice"] if answers else None,
            "effect_confidence": answers["effect"]["confidence"] if answers else None,
            "destructive_intent": answers["destructive_intent"]["noul"] if answers else None,
            "would_block": blocked,
            "block_reason": reason,
            "jev_model": response.get("model"),
        },
    )
    return blocked, reason


def cmd_ask(args) -> int:
    try:
        questions = parse_questions(args.q)
    except ValueError as e:
        return emit({"error": str(e)}, 2)
    if args.state is not None and len(args.state) > MAX_OWN_STATE_CHARS:
        return emit(
            {
                "error": f"state too long: {len(args.state)} chars, limit {MAX_OWN_STATE_CHARS}"
            },
            2,
        )
    if not has_key():
        return emit({"error": NO_KEY}, 78)
    cwd = Path(os.getcwd())
    root = repo_root(str(cwd))
    model = model_name(args.model)
    own = redact_deep(parse_own_state(args.state)) if args.state is not None else {}
    files, rels = {}, []
    if args.paths:
        rels, _ = prune(expand(args.paths, cwd, True), root)
        if len(rels) > MAX_ASK_FILES:
            return emit(
                {
                    "error": f"too many files: {len(rels)}; up to {MAX_ASK_FILES} per call",
                    "files": rels,
                },
                2,
            )
        for rel in rels:
            try:
                files[rel] = read_state(rel, root)["content"]
            except (OSError, ValueError) as e:
                return emit({"error": f"cannot read {rel}: {e}"}, 2)
    output = None
    if args.command is not None:
        try:
            blocked, reason = gate_command(args.command, cwd, root, model)
        except (RuntimeError, KeyError) as e:
            return emit(
                {
                    "error": f"gate failed, command not run: {redact(getattr(e, 'stderr', '')) or e}"
                },
                2,
            )
        if blocked:
            return emit({"error": f"blocked: {reason}. {BLOCK_NOTICE}"}, 2)
        try:
            done = subprocess.run(
                args.command,
                shell=True,
                cwd=root,
                timeout=60,
                capture_output=True,
                text=True,
                errors="replace",
                env={**os.environ, "CI": "1"},
            )
        except subprocess.TimeoutExpired:
            return emit({"error": "command timed out after 60 s"}, 2)
        output = redact_deep(
            {
                "command": "",
                "exit_code": done.returncode,
                "stdout": done.stdout[:200000],
                "stderr": done.stderr[:200000],
            }
        )
        output["command"] = command_view(args.command)[0]
    parts = {
        **{k: tokens(v) for k, v in own.items()},
        **{rel: tokens(text) for rel, text in files.items()},
    }
    if output is not None:
        parts["output"] = tokens(output)
    total = sum(parts.values())
    if total > STATE_TOKEN_BUDGET:
        return emit(
            {
                "error": f"over budget: {total} tokens, limit {STATE_TOKEN_BUDGET}",
                "parts": parts,
                "split": split_parts(parts, STATE_TOKEN_BUDGET),
            },
            2,
        )
    state = {
        **own,
        **({"files": files} if files else {}),
        **({"output": output} if output is not None else {}),
    }
    try:
        response = call(state, questions, job="ask_jev", model=model)
    except JevError as e:
        return emit({"error": f"jev: {redact(e.stderr) or e}"}, 2)
    return emit(
        {
            "answers": response["answers"],
            "state_summary": {
                "fields": list(own),
                "files": rels,
                "output": output is not None,
                "tokens": total,
            },
            "usage": response.get("usage"),
            "model": response.get("model"),
        }
    )


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"error": f"usage: {message}"}))
        sys.exit(64)


def main() -> None:
    parser = Parser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    files = sub.add_parser("files", help="one question set per file, in parallel")
    files.add_argument(
        "-r", "--recursive", action="store_true", help="expand directories recursively"
    )
    files.add_argument("-q", required=True, help="questions JSON object")
    files.add_argument("paths", nargs="+", metavar="PATH_OR_GLOB")
    files.set_defaults(func=cmd_files)
    pick = sub.add_parser("pick", help="choose the one file that fits a question")
    pick.add_argument("-q", required=True, help="question text")
    pick.add_argument("paths", nargs="*", metavar="PATH")
    pick.set_defaults(func=cmd_pick)
    ask = sub.add_parser(
        "ask", help="judge one situation from state, files, and a command's output"
    )
    ask.add_argument("-q", required=True, help="questions JSON object")
    ask.add_argument(
        "--state", help="your own state: JSON object, JSON list, or plain text"
    )
    ask.add_argument("--paths", nargs="+", help="files or globs to include (recursive)")
    ask.add_argument(
        "--command", help="shell command to gate, run, and include the output of"
    )
    ask.set_defaults(func=cmd_ask)
    for p in (files, pick, ask):
        p.add_argument("--model", help="Jev model (default: JEV_MODEL or jev-latest)")
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
