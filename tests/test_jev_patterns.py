"""Offline check for jev_patterns.call and its helpers, using a stub jev executable."""

import atexit
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).parents[1]
TMP = Path(tempfile.mkdtemp())
atexit.register(shutil.rmtree, TMP, True)
# DR-7: JEV resolves at import, so JEV_BIN must point at the stub before the import below.
os.environ["JEV_BIN"] = str(TMP / "jev")
sys.path.insert(0, str(ROOT))

import jev_patterns  # noqa: E402
from jev_patterns import (  # noqa: E402
    NO_KEY,
    PRICE_PER_MILLION_INPUT,
    JevError,
    call,
    estimated_usd,
    input_tokens,
    model_name,
)

# Records argv, stdin, and its exact inherited environment, then answers from cfg.json.
STUB = """#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
here = Path(__file__).parent
state = sys.stdin.read()
# /proc/self/environ is the block the child was started with, before Python's locale coercion edits it.
env = dict(kv.split("=", 1) for kv in Path("/proc/self/environ").read_text().split("\\0") if kv)
(here / "rec.json").write_text(json.dumps({"argv": sys.argv[1:], "stdin": state, "env": env, "sid": os.getsid(0)}))
cfg = json.loads((here / "cfg.json").read_text()) if (here / "cfg.json").exists() else {}
if cfg.get("sleep"):
    time.sleep(cfg["sleep"])
if cfg.get("stderr"):
    sys.stderr.write(cfg["stderr"])
if cfg.get("stderr_hex"):
    sys.stderr.buffer.write(bytes.fromhex(cfg["stderr_hex"]))
if cfg.get("exit"):
    sys.exit(cfg["exit"])
if "stdout" in cfg:
    print(cfg["stdout"])
    sys.exit(0)
print(json.dumps({"model": "typesafe/jev-stub", "answers": {"q": {"type": "noul", "noul": 0.8}},
                  "usage": {"input_tokens": 42}}))
"""
QUESTIONS = {"q": {"type": "noul", "instructions": "x"}}
# A distinct value per name, so each must arrive under its own name; the URLs carry credentials, as real ones can.
PROXY_ENV = {
    "HTTPS_PROXY": "http://user:pass@upper.proxy.example:3128",
    "https_proxy": "http://user:pass@lower.proxy.example:3128",
    "NO_PROXY": "localhost",
    "no_proxy": "127.0.0.1",
    "CURL_CA_BUNDLE": "/ca/curl-bundle.pem",
    "SSL_CERT_FILE": "/ca/ssl-cert.pem",
}
ALLOWED = {
    "PATH",
    "HOME",
    "USER",
    "SYSTEMROOT",
    "TMPDIR",
    "JEV_BASE_URL",
    "JEV_ALLOW_LOCAL",
    "TYPESAFE_API_KEY",
    "OPENROUTER_API_KEY",
    *PROXY_ENV,
}
# The host's own proxy settings are dropped too, so the checks below behave the same behind a proxy.
BASE = {
    k: v
    for k, v in os.environ.items()
    if k
    not in {
        "TYPESAFE_API_KEY",
        "OPENROUTER_API_KEY",
        "JEV_MODEL",
        "JEV_BASE_URL",
        "JEV_ALLOW_LOCAL",
        "GH_TOKEN",
        *PROXY_ENV,
    }
}

(TMP / "jev").write_text(STUB)
(TMP / "jev").chmod(0o755)


def use(cfg: dict | None = None, **env: str) -> None:
    """Reset the parent environment to BASE plus env, configure the stub, and clear its record."""
    os.environ.clear()
    os.environ.update(BASE, **env)
    (TMP / "cfg.json").write_text(json.dumps(cfg or {}))
    (TMP / "rec.json").unlink(missing_ok=True)


def rec() -> dict:
    return json.loads((TMP / "rec.json").read_text())


def raises(
    cfg: dict | None = None, timeout: float = jev_patterns.DEFAULT_TIMEOUT, **env: str
) -> JevError:
    use(cfg, **{"TYPESAFE_API_KEY": "k", **env})
    try:
        call({"a": 1}, QUESTIONS, job="t", timeout=timeout)
    except JevError as e:
        if not (cfg or {}).get("exit"):
            assert e.returncode is None and e.stderr == "", (str(e), e.returncode, e.stderr)
        return e
    raise AssertionError(f"call must raise JevError for {cfg}")


def check_call() -> None:
    """AC-1.1: argv, stdin, isolated environment, response and tokens."""
    use(
        GH_TOKEN="ghp_leak",
        TYPESAFE_API_KEY="k",
        JEV_MODEL="m1",
        JEV_BASE_URL="http://127.0.0.1:1",
        JEV_ALLOW_LOCAL="1",
    )
    response = call({"a": 1}, QUESTIONS, job="t")
    r = rec()
    assert r["argv"] == [
        "-m",
        "m1",
        "-q",
        '{"q": {"type": "noul", "instructions": "x"}}',
        "-j",
        "--",
        "t",
    ], r["argv"]
    assert json.loads(r["stdin"]) == {"a": 1}, r["stdin"]
    assert set(r["env"]) <= ALLOWED - {"OPENROUTER_API_KEY"}, sorted(r["env"])
    assert "GH_TOKEN" not in r["env"] and "JEV_MODEL" not in r["env"], sorted(r["env"])
    assert (
        r["env"]["TYPESAFE_API_KEY"] == "k"
        and r["env"]["JEV_BASE_URL"] == "http://127.0.0.1:1"
        and r["env"]["JEV_ALLOW_LOCAL"] == "1"
    ), r["env"]
    assert response["answers"] == {"q": {"type": "noul", "noul": 0.8}}, response
    assert isinstance(response["elapsed"], float), response
    assert input_tokens(response) == 42, response
    assert r["sid"] != os.getsid(0), "jev must run in its own session"

    use(TYPESAFE_API_KEY="k")
    call("PROMPT: x", QUESTIONS, job="t", model="m2")
    assert rec()["stdin"] == "PROMPT: x", rec()
    assert rec()["argv"][:2] == ["-m", "m2"], rec()["argv"]

    # the state is redacted here, so a caller that forgets cannot leak
    call("password=hunter2", QUESTIONS, job="t")
    assert rec()["stdin"] == "password=[REDACTED]", rec()
    call({"body": "ghp_abcdefghijklmnop", "token": "a b", "n": 1}, QUESTIONS, job="t")
    assert json.loads(rec()["stdin"]) == {"body": "[REDACTED]", "token": "[REDACTED]", "n": 1}, rec()
    call("token=x&&mark", QUESTIONS, job="t", redacted=True)
    assert rec()["stdin"] == "token=x&&mark", rec()


def check_proxy_env() -> None:
    """Proxy and CA settings reach jev so curl works behind a proxy; other secrets still do not."""
    # http_proxy stays out: every provider route is https, and SAFE_ENV lists only what jev needs.
    use(
        GH_TOKEN="ghp_leak",
        http_proxy="http://user:pass@plain.proxy.example:3128",
        TYPESAFE_API_KEY="k",
        **PROXY_ENV,
    )
    call({"a": 1}, QUESTIONS, job="t")
    env = rec()["env"]
    assert {k: env.get(k) for k in PROXY_ENV} == PROXY_ENV, sorted(env)
    assert "GH_TOKEN" not in env and "http_proxy" not in env, sorted(env)
    assert set(env) <= ALLOWED - {"OPENROUTER_API_KEY"}, sorted(env)

    # each only if set: a parent without a proxy passes none, not empty values
    use(GH_TOKEN="ghp_leak", TYPESAFE_API_KEY="k")
    call({"a": 1}, QUESTIONS, job="t")
    env = rec()["env"]
    assert not set(PROXY_ENV) & set(env), sorted(env)
    assert "GH_TOKEN" not in env, sorted(env)


def check_errors() -> None:
    """AC-1.2: every failure path is a JevError with a safe message."""
    e = raises({"exit": 2, "stderr": "\nFatal: Bearer secret_leaked_key\nmore"})
    assert str(e) == "jev exited 2; inspect provider access and limits locally", str(e)
    assert e.returncode == 2 and e.stderr == "Fatal: Bearer secret_leaked_key", (
        e.returncode,
        e.stderr,
    )
    assert "secret_leaked_key" not in str(e)
    assert len(raises({"exit": 1, "stderr": "x" * 500}).stderr) == 200
    e = raises({"exit": 2, "stderr_hex": "fffe0a"})
    assert e.returncode == 2 and e.stderr == "\ufffd\ufffd", (e.returncode, e.stderr)

    for env in ({}, {"TYPESAFE_API_KEY": "", "OPENROUTER_API_KEY": ""}):
        use(**env)
        try:
            call({"a": 1}, QUESTIONS, job="t")
            raise AssertionError("call must refuse without a key")
        except JevError as e:
            assert str(e) == NO_KEY and e.returncode is None and e.stderr == "", (
                str(e),
                e.returncode,
            )
        assert not (TMP / "rec.json").exists(), "stub must not run without a key"

    use(TYPESAFE_API_KEY="k", OPENROUTER_API_KEY="k2")
    call({"a": 1}, QUESTIONS, job="t")
    assert "OPENROUTER_API_KEY" not in rec()["env"], sorted(rec()["env"])

    use(TYPESAFE_API_KEY="", OPENROUTER_API_KEY="k2")
    call({"a": 1}, QUESTIONS, job="t")
    assert (
        rec()["env"].get("OPENROUTER_API_KEY") == "k2"
        and "TYPESAFE_API_KEY" not in rec()["env"]
    ), rec()["env"]

    assert str(raises({"sleep": 3}, timeout=0.5)) == "jev timed out after 0.5s"
    assert str(raises({"stdout": "not json"})) == "jev returned non-JSON output"
    # Python 3.12 rejects int literals over 4300 digits with a plain ValueError, not a JSONDecodeError.
    huge = '{"answers": {"q": {"noul": ' + "1" * 5000 + "}}}"
    assert str(raises({"stdout": huge})) == "jev returned non-JSON output"
    assert str(raises({"stdout": "[1]"})) == "jev response is not an object"
    assert str(raises({"stdout": "{}"})) == "jev response missing 'answers' object"
    assert (
        str(raises({"stdout": '{"answers": {}}'})) == "jev response missing answer 'q'"
    )
    assert (
        str(raises({"stdout": '{"answers": {"q": 1}}'}))
        == "jev response missing answer 'q'"
    )

    plain = TMP / "plain"
    plain.write_text(STUB)
    plain.chmod(0o644)
    jev_patterns.JEV, real = plain, jev_patterns.JEV
    try:
        e = raises()
        assert str(e).startswith("PermissionError:") and e.returncode is None, str(e)
    finally:
        jev_patterns.JEV = real


def check_helpers() -> None:
    use(JEV_MODEL="m3")
    assert model_name() == "m3" and model_name("x") == "x"
    use()
    assert model_name() == jev_patterns.DEFAULT_MODEL == "jev-latest"
    assert not jev_patterns.has_key()
    use(OPENROUTER_API_KEY="k2")
    assert jev_patterns.has_key()
    assert input_tokens({}) == 0 and input_tokens({"usage": None}) == 0
    assert input_tokens({"usage": {"input_tokens": None}}) == 0
    assert estimated_usd({"usage": {"input_tokens": 1_000_000}}) == PRICE_PER_MILLION_INPUT
    assert estimated_usd({}) == 0.0
    assert jev_patterns.JEV == TMP / "jev"
    assert isinstance(JevError("x"), RuntimeError)


def check_job_positional() -> None:
    """#80: call()'s argv, fed to the real bin/jev as a dry run, sends {model, state, questions} and no job."""
    job = "JOB-LABEL-MARKER"
    use(TYPESAFE_API_KEY="k", JEV_MODEL="m1")
    call({"a": 1}, QUESTIONS, job=job)
    r = rec()
    # -j is jev's bare full-JSON flag; "--" ends the options, and the job is the positional <question> after them.
    assert r["argv"][-3:] == ["-j", "--", job], r["argv"]
    # -n prints the request body and sends nothing; no key reaches the real script.
    dry = subprocess.run(
        [str(ROOT / "bin/jev"), "-n", *r["argv"]],
        input=r["stdin"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"]},
        timeout=10,
        check=False,
    )
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout) == {"model": "m1", "state": {"a": 1}, "questions": QUESTIONS}, dry.stdout
    assert job not in dry.stdout + dry.stderr, "the job must not reach the request"
    # Without the positional, jev refuses with usage (exit 64): the job is what satisfies it.
    bare = subprocess.run(
        [str(ROOT / "bin/jev"), "-n", *r["argv"][:-1]],
        input=r["stdin"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"]},
        timeout=10,
        check=False,
    )
    assert bare.returncode == 64, (bare.returncode, bare.stdout)
    # A job that starts with "-" must not be parsed as jev options ("-x" would be an unknown flag, "-n" a dry run).
    for dash_job in ("-x", "-n", "--"):
        call({"a": 1}, QUESTIONS, job=dash_job)
        r = rec()
        assert r["argv"][-1] == dash_job, r["argv"]
        dry = subprocess.run(
            [str(ROOT / "bin/jev"), "-n", *r["argv"]],
            input=r["stdin"],
            capture_output=True,
            text=True,
            env={"PATH": os.environ["PATH"]},
            timeout=10,
            check=False,
        )
        assert dry.returncode == 0, (dash_job, dry.returncode, dry.stderr)
        assert json.loads(dry.stdout)["questions"] == QUESTIONS, dry.stdout


def check_structure() -> None:
    """AC-1.4: the sentinel's only subprocess.run is git, it has no "-j", and the library is stdlib-only."""
    sentinel = (ROOT / "scope_sentinel.py").read_text().splitlines()
    runs = [line for line in sentinel if "subprocess.run" in line]
    assert len(runs) == 1 and "rev-parse" in runs[0], runs
    assert not [line for line in sentinel if '"-j"' in line], (
        "sentinel must not build a jev argv"
    )
    for name, allowed in (("jev_patterns.py", {"redaction"}), ("redaction.py", set())):
        imports = re.findall(
            r"^(?:from|import)\s+(\w+)", (ROOT / name).read_text(), re.M
        )
        assert imports and set(imports) <= sys.stdlib_module_names | allowed, imports


if __name__ == "__main__":
    for check in (check_call, check_proxy_env, check_errors, check_helpers, check_job_positional, check_structure):
        check()
    print("jev_patterns ok")
