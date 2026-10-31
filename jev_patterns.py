"""The one Jev transport: every Jev call in the repo goes through call().

- call runs JEV -m <model> -q <questions JSON> -j <job> with the state on stdin
  (a str verbatim, anything else JSON-encoded), one attempt, default timeout 40 s.
- The child environment is SAFE_ENV (each only if set) plus one key: TYPESAFE_API_KEY when
  non-empty, else OPENROUTER_API_KEY when non-empty. JEV_MODEL travels as -m, never in env.
- str(JevError) is the safe message and never contains jev's stderr; stderr is reachable only
  as JevError.stderr (first non-empty line, at most 200 characters).
- JEV, DEFAULT_MODEL, and NO_KEY are defined here once, at import: set JEV_BIN before importing.
"""

import json
import os
from pathlib import Path
import subprocess
import time

JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")
DEFAULT_MODEL = "jev-latest"
DEFAULT_TIMEOUT = 40.0
NO_KEY = (
    "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"
)
SAFE_ENV = (
    "PATH",
    "HOME",
    "USER",
    "SYSTEMROOT",
    "TMPDIR",
    "JEV_BASE_URL",
    "JEV_ALLOW_LOCAL",
)


class JevError(RuntimeError):
    def __init__(
        self, message: str, *, returncode: int | None = None, stderr: str = ""
    ):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def has_key() -> bool:
    return bool(
        os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    )


def model_name(model: str | None = None) -> str:
    return model or os.environ.get("JEV_MODEL") or DEFAULT_MODEL


def isolated_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in SAFE_ENV if k in os.environ}
    for key in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY"):
        if os.environ.get(key):
            env[key] = os.environ[key]
            return env
    raise JevError(NO_KEY)


def input_tokens(response: dict) -> int:
    return int((response.get("usage") or {}).get("input_tokens") or 0)


PRICE_PER_MILLION_INPUT = 0.042


def estimated_usd(response: dict) -> float:
    return input_tokens(response) * PRICE_PER_MILLION_INPUT / 1_000_000


def call(
    state,
    questions: dict,
    *,
    job: str,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """One Jev call: the parsed response with every question id answered, plus "elapsed" seconds."""
    env = isolated_env()
    stdin = state if isinstance(state, str) else json.dumps(state)
    start = time.perf_counter()
    try:
        process = subprocess.run(
            [str(JEV), "-m", model_name(model), "-q", json.dumps(questions), "-j", job],
            input=stdin,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
            start_new_session=True,
            check=False,
        )
    except OSError as e:
        raise JevError(f"{type(e).__name__}: {e}") from None
    except subprocess.TimeoutExpired:
        raise JevError(f"jev timed out after {timeout:g}s") from None
    elapsed = time.perf_counter() - start
    if process.returncode:
        first = next((line for line in process.stderr.splitlines() if line.strip()), "")
        raise JevError(
            f"jev exited {process.returncode}; inspect provider access and limits locally",
            returncode=process.returncode,
            stderr=first[:200],
        )
    try:
        response = json.loads(process.stdout)
    except (ValueError, RecursionError):
        raise JevError("jev returned non-JSON output") from None
    if not isinstance(response, dict):
        raise JevError("jev response is not an object")
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise JevError("jev response missing 'answers' object")
    for qid in questions:
        if not isinstance(answers.get(qid), dict):
            raise JevError(f"jev response missing answer {qid!r}")
    response["elapsed"] = elapsed
    return response
