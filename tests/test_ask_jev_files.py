"""Offline check for ask_jev_files.py: tmp git repo, script run by absolute path, stub jev that records its state."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).parents[1] / "ask_jev_files.py"
BLOCK_NOTICE = (
    "This block is final. Do not try to work around it with another command, another tool, a different path, "
    "or an encoding that does the same thing. Stop and tell the user what was blocked and why."
)

# Records job, argv and stdin per call next to itself, then answers from cfg.json.
STUB = """#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
here = Path(__file__).parent
state = sys.stdin.read()
argv = sys.argv[1:]
questions = json.loads(argv[argv.index("-q") + 1])
job = argv[-1]  # jev_patterns.call ends argv with the job positional; -j is a bare flag
(here / f"rec-{time.time_ns()}-{os.getpid()}.json").write_text(
    json.dumps({"job": job, "questions": questions, "state": json.loads(state)}))
cfg = json.loads((here / "cfg.json").read_text()) if (here / "cfg.json").exists() else {}
if cfg.get("fail"):
    print(cfg["fail"], file=sys.stderr)
    sys.exit(2)
answers = {}
for qid, q in questions.items():
    if qid == "effect":
        e, c = cfg.get("effect", "read_only"), cfg.get("effect_confidence", 0.95)
        answers[qid] = {"type": "choice", "choice": e, "confidence": c, "probabilities": {e: c - 0.05}}
    elif qid == "destructive_intent":
        answers[qid] = {"type": "noul", "noul": cfg.get("destructive", 0.05)}
    elif qid == "pick":
        p, c = cfg.get("pick", "none"), cfg.get("pick_confidence", 0.9)
        answers[qid] = {"type": "choice", "choice": p, "confidence": c, "probabilities": {p: c}}
    elif q["type"] == "choice":
        k = next(iter(q["criteria"]))
        answers[qid] = {"type": "choice", "choice": k, "confidence": 0.8, "probabilities": {k: 0.75}}
    elif q["type"] == "score":
        answers[qid] = {"type": "score", "score": 2.5}
    else:
        answers[qid] = {"type": "noul", "noul": 0.5}
print(json.dumps({"model": "typesafe/jev-stub-1", "answers": answers, "usage": {"input_tokens": 9}}))
"""

HOOKS_Q = json.dumps(
    {"relevant": {"type": "noul", "instructions": "Is this file about hooks?"}}
)


class Env:
    """A tmp git repo plus a stub jev; run() executes the script by absolute path with cwd in the repo."""

    def __init__(self, tmp: str):
        self.repo = Path(tmp) / "repo"
        self.stub_dir = Path(tmp) / "stub"
        self.repo.mkdir(parents=True)
        self.stub_dir.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.stub_dir / "jev").write_text(STUB)
        (self.stub_dir / "jev").chmod(0o755)

    def cfg(self, **kw):
        (self.stub_dir / "cfg.json").write_text(json.dumps(kw))

    def records(self, job=None):
        recs = [
            json.loads(p.read_text()) for p in sorted(self.stub_dir.glob("rec-*.json"))
        ]
        return [r for r in recs if job is None or r["job"] == job]

    def write(self, rel, text="x\n", size=None):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if size is None else "a" * size)

    def run(self, *args, keys=True):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "JEV_LOG_DIR")
        }
        env["JEV_BIN"] = str(self.stub_dir / "jev")
        if keys:
            env["TYPESAFE_API_KEY"] = "stub-key"
        done = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return done.returncode, json.loads(done.stdout)

    def sentinel_rows(self):
        log = self.repo / ".local" / "sentinel.jsonl"
        return (
            [json.loads(line) for line in log.read_text().splitlines()]
            if log.exists()
            else []
        )


def load_module(env: Env):
    os.environ["JEV_BIN"] = str(env.stub_dir / "jev")
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("ask_jev_files", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_files(tmp):
    env = Env(tmp)
    for name in ("a.txt", "b.txt", "c.txt"):
        env.write(name, f"hooks in {name}\n")
    env.write("empty.txt", "")
    (env.repo / "img.png").write_bytes(b"\x89PNG data")
    env.write("node_modules/x.js", "module.exports = 1\n")
    env.write("big.txt", size=300000)
    for i in range(20):
        env.write(f"many/f{i:02d}.txt", f"small {i}\n")
    code, out = env.run("files", "-r", "-q", HOOKS_Q, ".")
    assert code == 0, out
    paths = [r["path"] for r in out["results"]]
    assert len(paths) == 23 and paths == sorted(paths), paths
    assert "big.txt" not in paths and "img.png" not in paths
    assert out["results"][0]["answers"]["relevant"]["noul"] == 0.5
    reasons = sorted(s["reason"] for s in out["skipped"])
    assert reasons == sorted(
        ["empty", "binary or lock file", "skipped directory", "too large, 300000 bytes"]
    ), reasons
    assert out["calls"] == 23 and out["model"] == "typesafe/jev-stub-1", out
    recs = env.records("ask_jev_files")
    assert len(recs) == 23
    for r in recs:
        assert set(r["state"]) == {"path", "content"}
        assert r["state"]["content"] == (env.repo / r["state"]["path"]).read_text()
        assert r["questions"] == json.loads(HOOKS_Q)


def check_files_edges(tmp):
    env = Env(tmp)
    env.write("a.txt")
    env.write("sub/b.txt")
    env.write(".hidden")
    # a directory without -r expands to dir/* : one level, no dotfiles
    code, out = env.run("files", "-q", HOOKS_Q, ".")
    assert code == 0 and [r["path"] for r in out["results"]] == ["a.txt"], out
    # glob patterns are expanded; nothing matching -> zero calls
    code, out = env.run("files", "-q", HOOKS_Q, "nothing/*.zzz")
    assert code == 0 and out["results"] == [] and out["calls"] == 0, out
    # a binary file by NUL bytes is skipped at read time
    (env.repo / "blob.dat").write_bytes(b"ab\x00cd")
    code, out = env.run("files", "-q", HOOKS_Q, "blob.dat")
    assert out["skipped"] == [{"path": "blob.dat", "reason": "binary"}], out
    # a provider failure becomes a skipped reason, not a crash
    env.cfg(fail="HTTP 429 rate limited\nsecond line")
    code, out = env.run("files", "-q", HOOKS_Q, "a.txt")
    assert code == 0 and out["results"] == [], out
    assert out["skipped"] == [
        {"path": "a.txt", "reason": "jev: HTTP 429 rate limited"}
    ], out
    # an empty-string secret in a file reaches Jev redacted
    env.cfg()
    env.write("s.txt", "password=hunter2secret\n")
    env.run("files", "-q", HOOKS_Q, "s.txt")
    assert "hunter2secret" not in env.records()[-1]["state"]["content"]


def check_pick(tmp):
    env = Env(tmp)
    for name in ("a.py", "b.py", "c.py"):
        env.write(name)
    paths = ["a.py", "b.py", "c.py"]
    env.cfg(pick="b.py", pick_confidence=0.40)
    code, out = env.run("pick", "-q", "Which file is the entry point?", *paths)
    assert code == 0 and out["path"] == "b.py" and out["skipped"] == [], out
    rec = env.records("ask_jev_pick")[-1]
    assert rec["state"] == {
        "question": "Which file is the entry point?",
        "files": paths,
    }
    assert rec["questions"]["pick"]["criteria"] == {
        "a.py": None,
        "b.py": None,
        "c.py": None,
        "none": "No file in the list fits",
    }
    env.cfg(pick="none", pick_confidence=0.9)
    assert env.run("pick", "-q", "Q?", *paths)[1]["path"] is None
    env.cfg(pick="b.py", pick_confidence=0.20)
    assert env.run("pick", "-q", "Q?", *paths)[1]["path"] is None
    env.cfg(pick="b.py", pick_confidence=0.30)
    assert env.run("pick", "-q", "Q?", *paths)[1]["path"] == "b.py"
    before = len(env.records())
    code, out = env.run("pick", "-q", "Q?", "/etc/hosts", "missing.py")
    assert (
        code == 0
        and out["path"] is None
        and out["confidence"] == 0
        and out["probabilities"] == {}
    ), out
    assert {s["reason"] for s in out["skipped"]} == {"outside the repo", "not found"}, (
        out
    )
    code, out = env.run("pick", "-q", "Q?")
    assert code == 0 and out["path"] is None and out["skipped"] == []
    assert len(env.records()) == before, "no stub call for zero candidates"


def check_ask(tmp):
    env = Env(tmp)
    env.write("a.py", "def f():\n    pass\n")
    q = {
        "bug": {
            "type": "noul",
            "instructions": "Does `report` describe a bug in `files`?",
        },
        "ran": {
            "type": "choice",
            "instructions": "Did `output` succeed?",
            "criteria": {
                "yes": "exit_code 0",
                "no": "non-zero exit",
                "other": "cannot tell",
            },
        },
    }
    code, out = env.run(
        "ask",
        "--state",
        '{"report":"export fails"}',
        "--paths",
        "a.py",
        "--command",
        "echo hi",
        "-q",
        json.dumps(q),
    )
    assert code == 0, out
    gate = env.records("ask_jev_gate")[-1]
    assert gate["state"] == {"command": "echo hi", "cwd": os.path.realpath(env.repo)}, (
        gate
    )
    assert set(gate["questions"]) == {"effect", "destructive_intent"}
    final = env.records("ask_jev")[-1]
    assert set(final["state"]) == {"report", "files", "output"}, final["state"]
    assert final["state"]["files"] == {"a.py": "def f():\n    pass\n"}
    assert (
        final["state"]["output"]["exit_code"] == 0
        and final["state"]["output"]["stdout"] == "hi\n"
    )
    assert set(out["answers"]) == {"bug", "ran"}
    summary = out["state_summary"]
    assert (
        summary["fields"] == ["report"]
        and summary["files"] == ["a.py"]
        and summary["output"] is True
    )
    assert (
        summary["tokens"] > 0
        and out["model"] == "typesafe/jev-stub-1"
        and out["usage"] == {"input_tokens": 9}
    )
    rows = env.sentinel_rows()
    assert len(rows) == 1, rows
    row = rows[0]
    assert (
        row["host"] == "cli"
        and row["source"] == "ask_jev_files"
        and row["would_block"] is False
    ), row
    assert (
        row["gate"] == "bash"
        and row["command"] == "echo hi"
        and row["effect"] == "read_only"
    ), row
    assert (
        row["host_model"] is None
        and row["jev_model"] == "typesafe/jev-stub-1"
        and "scope" not in row
    )


def check_ask_state_shapes(tmp):
    env = Env(tmp)
    q = json.dumps({"x": {"type": "noul", "instructions": "Is `text` ok?"}})
    env.run("ask", "--state", "plain words", "-q", q)
    assert env.records("ask_jev")[-1]["state"] == {"text": "plain words"}
    env.run("ask", "--state", "[1, 2]", "-q", q)
    assert env.records("ask_jev")[-1]["state"] == {"items": [1, 2]}
    env.run("ask", "--state", '{"note": "token=abc123def456"}', "-q", q)
    assert "abc123def456" not in json.dumps(env.records("ask_jev")[-1]["state"])
    code, out = env.run("ask", "--state", "x" * 8001, "-q", q)
    assert code == 2 and out["error"] == "state too long: 8001 chars, limit 8000", out
    code, out = env.run("ask", "--command", "false", "-q", q)
    assert code == 0 and env.records("ask_jev")[-1]["state"]["output"]["exit_code"] == 1


def check_ask_blocked(tmp):
    env = Env(tmp)
    env.cfg(effect="irreversible", effect_confidence=0.90)
    q = json.dumps({"x": {"type": "noul", "instructions": "ok?"}})
    code, out = env.run("ask", "--command", "rm -rf build && touch marker-ran", "-q", q)
    assert code == 2, out
    assert out == {
        "error": "blocked: irreversible (0.90): nothing would restore what this removes or "
        "overwrites. " + BLOCK_NOTICE
    }, out
    assert not (env.repo / "marker-ran").exists(), "a blocked command must not run"
    assert not env.records("ask_jev"), "no final call after a block"
    rows = env.sentinel_rows()
    assert (
        len(rows) == 1
        and rows[0]["would_block"] is True
        and rows[0]["source"] == "ask_jev_files"
    ), rows
    assert rows[0]["host"] == "cli" and rows[0]["risky"] is True, rows
    assert rows[0]["block_reason"].startswith("irreversible (0.90)")


def check_ask_limits(tmp):
    env = Env(tmp)
    q = json.dumps({"x": {"type": "noul", "instructions": "ok?"}})
    for i in range(21):
        env.write(f"f{i:02d}.txt")
    code, out = env.run("ask", "--paths", ".", "-q", q)
    assert (
        code == 2
        and out["error"] == "too many files: 21; up to 20 per call"
        and len(out["files"]) == 21
    ), out
    env2 = Env(tmp + "/b")
    for i in range(3):
        env2.write(f"big{i}.txt", size=81000)
    code, out = env2.run("ask", "--paths", ".", "-q", q)
    assert (
        code == 2
        and out["error"].startswith("over budget: ")
        and out["error"].endswith("limit 60000")
    ), out
    bins = out["split"]
    assert sorted(n for b in bins for n in b) == sorted(out["parts"]), bins
    assert all(sum(out["parts"][n] for n in b) <= 60000 for b in bins), (
        bins,
        out["parts"],
    )
    assert len(bins) == 2 and not env2.records("ask_jev"), "nothing is sent over budget"
    code, out = env2.run("ask", "--paths", "big0.txt", "-q", q)
    assert code == 0, out


def check_errors(tmp):
    env = Env(tmp)
    env.write("a.txt")
    for bad in (
        "[]",
        "not json",
        "{}",
        json.dumps({"q": {"type": "bogus", "instructions": "x"}}),
        json.dumps({"q": {"type": "noul"}}),
        json.dumps({"q": {"type": "choice", "instructions": "x"}}),
        json.dumps({"q": {"type": "choice", "instructions": "x", "criteria": {}}}),
        json.dumps(
            {"q": {"type": "score", "instructions": "x", "criteria": ["only one"]}}
        ),
    ):
        for cmd in (["files", "a.txt"], ["ask"]):
            code, out = env.run(cmd[0], "-q", bad, *cmd[1:])
            assert code == 2 and out["error"].startswith("invalid questions_json"), (
                bad,
                cmd,
                out,
            )
    assert not env.records(), "questions are validated before any call"
    code, out = env.run("files", "-q", HOOKS_Q, "a.txt", keys=False)
    assert code == 78 and "key" in out["error"], out
    code, out = env.run("files")
    assert code == 64 and "error" in out, out
    score = json.dumps(
        {"s": {"type": "score", "instructions": "x", "criteria": ["lo", "hi"]}}
    )
    assert env.run("files", "-q", score, "a.txt")[0] == 0


def check_units(tmp):
    env = Env(tmp)
    mod = load_module(env)
    assert mod.split_parts({"a": 60000}, 60000) == [["a"]]
    assert mod.split_parts({"a": 30000, "b": 30000, "c": 1000}, 60000) == [
        ["a", "b"],
        ["c"],
    ]
    assert mod.split_parts({"a": 70000, "b": 1}, 60000) == [["a"], ["b"]]
    assert (
        mod.MAX_FILE_CHARS,
        mod.MAX_FILES,
        mod.MAX_ASK_FILES,
        mod.STATE_TOKEN_BUDGET,
    ) == (240000, 255, 20, 60000)
    assert (mod.MAX_OWN_STATE_CHARS, mod.PICK_FLOOR, mod.WORKERS) == (8000, 0.3, 16)
    # prune: 240000 bytes kept, 240001 skipped
    env.write("edge.txt", size=240000)
    env.write("over.txt", size=240001)
    kept, skipped = mod.prune(
        [str(env.repo / "edge.txt"), str(env.repo / "over.txt")], env.repo
    )
    assert kept == ["edge.txt"] and skipped == [
        {"path": "over.txt", "reason": "too large, 240001 bytes"}
    ]
    # prune: 255 kept, the 256th is capped
    names = []
    for i in range(256):
        env.write(f"n/{i:03d}.txt")
        names.append(str(env.repo / f"n/{i:03d}.txt"))
    kept, skipped = mod.prune(names, env.repo)
    assert len(kept) == 255 and skipped == [
        {"path": "n/255.txt", "reason": "over the 255 file cap; narrow the pattern"}
    ]
    # read_state refuses NUL bytes
    (env.repo / "bin.dat").write_bytes(b"\x00\x01")
    try:
        mod.read_state("bin.dat", env.repo)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert str(e) == "binary"
    # invalid utf-8 is replaced, not fatal
    (env.repo / "latin.txt").write_bytes(b"caf\xe9\n")
    assert mod.read_state("latin.txt", env.repo) == {
        "path": "latin.txt",
        "content": "caf�\n",
    }
    assert mod.expand(["*.nomatch"], env.repo, False) == []


def main():
    for check in (
        check_units,
        check_files,
        check_files_edges,
        check_pick,
        check_ask,
        check_ask_state_shapes,
        check_ask_blocked,
        check_ask_limits,
        check_errors,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            check(tmp)
        print(f"ok {check.__name__}")
    print("all ask_jev_files checks passed")


if __name__ == "__main__":
    main()
