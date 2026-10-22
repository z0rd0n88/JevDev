# Spec — `jev_patterns.py`: one Jev invocation path for JevDev

## 1. Context & Problem Statement

JevDev runs Jev (TypeSafe's System One decision model) from six Python entry points: two hooks (`scope_sentinel.py`, `compact_advisor.py`), one hook-plus-CLI (`skill_router.py`), and three CLIs (`ask_jev_files.py`, `fixture_curator.py`, `handoff_check.py`). Every one of them reaches Jev the same way: a `subprocess.run` of `~/.local/bin/jev` with `-m <model> -q <questions JSON> -j <job>` and the state on stdin. disler/ten-levels-of-jev (MIT, commit `777adaf`, cloned to `/tmp/ten-levels-src`) calls levels 1 to 5 "Jev from code": one client (`apps/ten-levels/src/core/client.ts`) and plain functions that own the thresholds. Levels 6 to 10 were ported by `docs/specs/ten-levels-port.md` (PRs #30 to #37). The repo has no equivalent of the client: each caller carries its own copy.

**Observed behaviour today**

- Six copies of the Jev subprocess call exist: `scope_sentinel.py:232-253`, `ask_jev_files.py:159-179`, `compact_advisor.py:143-172`, `skill_router.py:279-302`, `fixture_curator.py:67-93`, `handoff_check.py:142-200`. The brief named four; `fixture_curator.py` and `handoff_check.py` were found by `grep -n 'subprocess.run' *.py` on 2026-10-16.
- They disagree on error policy. Five hide `jev`'s stderr behind `jev exited N; inspect provider access and limits locally` (`scope_sentinel.py:249-252`, `compact_advisor.py:167-170`, `skill_router.py:296-301`, `fixture_curator.py:89-91`, `handoff_check.py:190-192`); one surfaces the first stderr line (`ask_jev_files.py:172-175`). Two catch a timeout (`ask_jev_files.py:170-171`, `handoff_check.py:185-186`); four let `subprocess.TimeoutExpired` propagate.
- They disagree on what the Jev process may see. `handoff_check.py:69-84,182` passes an allow-listed environment to `jev`; the other five inherit the whole process environment, which in a Claude session carries `GH_TOKEN`, `DISCORD_BOT_TOKEN`, and `RUNPOD_API_KEY` from the user's `settings.local.json` `env` block (`/home/alex/AGENTS.md`, Secrets section). `with_jev_key.sh:3-7` adds the Jev key from `~/.secrets` and `exec`s; it removes nothing.
- They disagree on response validation. `ask_jev_files.py:256` reads `response["answers"]` outside the `try` at `:244-247`, so a zero-exit `jev` whose stdout lacks `answers` ends `files` with a `KeyError` traceback and exit 1 instead of the documented `{"error": …}` JSON (`ask_jev_files.py:8`). `handoff_check.py:194-220` validates the envelope, each item, and the verdict; the hooks log a `KeyError` row (`scope_sentinel.py:522-524`, `compact_advisor.py:228-231`).
- Two readers of `usage.input_tokens` raise on `"usage": null` (`scope_sentinel.py:268,289` and `skill_router.py:305-306` use `.get("usage", {})`); four guard with `or {}` (`compact_advisor.py:215-217`, `fixture_curator.py:99`, `handoff_check.py:231-232`).
- Level 3 (composite scoring) and level 5 (routing) exist only inside `skill_router.py` (`:321-325` gate average, `:339` threshold, `:365-369` fits floor). Issue #28 (agy host) would copy them.

**Why it matters.** Issue #17 graduates the gates from shadow to live on the strength of the sentinel rows; every fix to the Jev transport (isolation, timeouts, malformed responses) today lands in one of six places and drifts in the other five. The next Jev caller (issue #28, any new hook) starts by copying `skill_router.py:279-302`, making a seventh. The cost of leaving it alone is paying the `handoff_check.py` hardening review again per caller.

**Success metrics**

- Offline: `python3 tests/test_jev_patterns.py` passes with a stub `jev` on `JEV_BIN` and no network; every pre-existing `tests/test_*.py` passes with its assertions untouched (loader lines may change, §8).
- Structural: after Phase 4, `grep -n '"-j"' *.py` (the `jev` job flag, present in all six argv builds today and in no other code) returns exactly one line, in `jev_patterns.py`.
- Live: one smoke per phase (`smoke.sh` for the hooks and the CLI, the `route` command for the router) recorded in the PR body with `jev_model` matching `^typesafe/jev-`.

## 2. Current Architecture

**Files**

| File | Job | Cite |
|---|---|---|
| `scope_sentinel.py` | PreToolUse shadow hook and manual CLI; `run_jev` is the subprocess call; `judge_write` and `judge_bash` read the response | `:232-253`, `:256-270`, `:273-291`, `:495-525` |
| `ask_jev_files.py` | `files` / `pick` / `ask` CLI; `jev_call` is the subprocess call; `has_key`, `model_of`, `NO_KEY` are its own copies | `:159-179`, `:201-208`, `:60-62`; call sites `:245`, `:286-291`, `:321-326`, `:445` |
| `compact_advisor.py` | Stop hook; `ask_jev` is the subprocess call | `:143-172`; call site `:212`; imports `:14-24` |
| `skill_router.py` | UserPromptSubmit hook and `route` / `measure` / `benchmark` / `score` CLI; `jev` is the subprocess call; `usage_tokens` reads usage | `:279-302`, `:305-306`, `:309-379`; constants `:26-27`; hook `:781-812`; CLI error handler `:885-887` |
| `fixture_curator.py` | benchmark fixture curation CLI; `curate_with_jev` is the subprocess call; `score` is the strict noul reader | `:67-100`, `:59-64`; constants `:18-19`; loop `:169-176` |
| `handoff_check.py` | handoff integrity CLI; `resolve_jev_binary`, `get_isolated_env`, `evaluate_handoff` | `:63-66`, `:69-84`, `:142-238`; `--timeout` `:246` |
| `with_jev_key.sh` | loads `TYPESAFE_API_KEY` / `OPENROUTER_API_KEY` from `~/.secrets`, then `exec "$@"`; the rest of the environment passes through | `:3-7` |
| `~/.local/bin/jev` | bash client: `getopts ':c:s:q:m:jnh'`; a state starting with `{` or `[` that `jq -e .` accepts is sent as JSON; key from `TYPESAFE_API_KEY` then `OPENROUTER_API_KEY`; route by key prefix or `JEV_BASE_URL`; `curl -sS --fail-with-body -m 30`; on curl failure prints the response body to stderr and exits 2; no key exits 78 | `jev:45`, `:68`, `:86`, `:88-95`, `:99`, `:101-104` |
| `install_user.py` | user-scope installer; hooks run `python3 {jevdev}/<script> hook <host> --user` from the primary checkout | `:14`, `:24-28` |
| `.claude/settings.json`, `.codex/config.toml`, `.agents/hooks.json` | project hooks run the scripts by absolute path through `with_jev_key.sh` | `.claude/settings.json:11,23,33,44`; `.codex/config.toml:5,14,22,29`; `.agents/hooks.json:9,19` |

**Call flow (Claude, one Bash command)**

1. Claude runs `bash with_jev_key.sh python3 scope_sentinel.py hook` (`.claude/settings.json:23`); the wrapper adds the Jev key and execs (`with_jev_key.sh:3-7`).
2. `run_hook` detaches a `judge` child with the event on stdin and returns (`scope_sentinel.py:470-492`).
3. `run_judge` builds the row, scans the transcript, takes a judge slot, and calls `judge_bash` (`:495-525`).
4. `judge_bash` builds the JSON state and calls `run_jev({"scope": …, **BASH_QUESTIONS}, state)` (`:273-276`).
5. `run_jev` checks the key, resolves the model, runs `[JEV, "-m", model, "-q", json.dumps(questions), "-j", "scope_sentinel"]` with `input=json.dumps(state)`, `timeout=40`, inherited environment; raises `RuntimeError` on a non-zero exit; returns `(json.loads(stdout), elapsed)` (`:232-253`).
6. `judge_bash` reads `response["answers"]`, applies `gate_bash`, and reads `response.get("usage", {}).get("input_tokens")` (`:277-291`); any exception becomes the row's `error` as `f"{type(e).__name__}: {e}"` (`:522-524`).

**Data shapes**

Jev request `{"model", "state", "questions"}` and response `{"model", "answers": {id: {...}}, "usage": {"input_tokens", "output_tokens", "cost"}, "id", "provider"}` as recorded in `docs/specs/ten-levels-port.md:55` (probed live 2026-10-15); the request shape was re-confirmed with `jev -n` on 2026-10-16. Each caller's call today:

| Caller | State | `-j` job | Model | Timeout | Env | On non-zero exit | On timeout | On missing answer |
|---|---|---|---|---|---|---|---|---|
| `scope_sentinel.run_jev` `:232-253` | `json.dumps(dict)` | `scope_sentinel` | `JEV_MODEL` or `jev-latest` `:238` | 40 | inherited | `RuntimeError`, stderr hidden `:249-252` | propagates `TimeoutExpired` → row `error` `:522-524` | `KeyError` → row `error` |
| `ask_jev_files.jev_call` `:159-179` | `json.dumps(any)` | caller-chosen (`ask_jev_files`, `ask_jev_pick`, `ask_jev_gate`, `ask_jev`) | `--model` or `JEV_MODEL` or default `:207-208` | 40 | inherited | `RuntimeError(first stderr line)` `:172-175` | `RuntimeError("TimeoutExpired: …")` `:170-171` | `files`: `KeyError` traceback `:256`; `pick`: caught `:292-293`; `ask`: `KeyError` traceback `:450` |
| `compact_advisor.ask_jev` `:143-172` | `json.dumps(dict)` | `compact_advisor` | `JEV_MODEL` or default `:154` | 40 | inherited | `RuntimeError`, hidden `:167-170` | propagates → row `error` `:228-231` | `KeyError` → row `error` |
| `skill_router.jev` `:279-302` | `json.dumps({"request", "recent_context"})` | `routing` | `JEV_MODEL` or default `:285` | 40 | inherited | `RuntimeError`, hidden `:296-301` | propagates → hook `systemMessage` `:806-812`, CLI exit 2 `:885-887` | `KeyError` → same handlers |
| `fixture_curator.curate_with_jev` `:67-100` | plain string `PROMPT TEXT:\n…` `:74` | `curator` | `JEV_MODEL` or default `:76` | 40 | inherited | `RuntimeError`, hidden `:89-91` | propagates → `ERROR:` line, counted failed `:173-176` | `KeyError` → counted failed |
| `handoff_check.evaluate_handoff` `:142-238` | plain string with `<untrusted_handoff>` `:164-169` | `handoff_check` | `--model` or `JEV_MODEL` or default `:161` | `--timeout` (40.0) `:146,246` | allow-list `:69-84,182` + `start_new_session=True` `:181` | `RuntimeError`, hidden `:190-192` | `RuntimeError("jev timed out …")` `:185-186` | `RuntimeError("Missing evaluation answer …")` `:209-210` |

`JEV` is resolved four times (`scope_sentinel.py:19`, `skill_router.py:26`, `fixture_curator.py:19`, `handoff_check.py:63-66`; `ask_jev_files.py:28` and `compact_advisor.py:16` import the sentinel's). The key check is written six times (`scope_sentinel.py:234`, `ask_jev_files.py:201-204`, `compact_advisor.py:145`, `skill_router.py:280`, `fixture_curator.py:69`, `handoff_check.py:74-79`). The model is resolved nine times (`scope_sentinel.py:238,498`, `ask_jev_files.py:208`, `compact_advisor.py:154,181`, `skill_router.py:285,328`, `fixture_curator.py:76`, `handoff_check.py:161`). `usage.input_tokens` is read six times (`scope_sentinel.py:268,289`, `compact_advisor.py:215-217`, `skill_router.py:305-306`, `fixture_curator.py:99`, `handoff_check.py:231-232`). Question validation is not duplicated: only `ask_jev_files.py:128-156` validates, because only it takes questions from the user.

**Real vs. mocked.** Every call above is a live `subprocess.run` of the real `jev` script. Tests replace the binary through `JEV_BIN` with a Python stub (`tests/test_sentinel.py:12-57,86`, `tests/test_ask_jev_files.py:20-50,89`, `tests/test_compact.py:17-34,126`, `tests/test_fixture_curator.py:68-86`, `tests/test_handoff_check.py:114-166`). `tests/test_router.py:55-61` runs the real `jev` script against a local `ThreadingHTTPServer` selected by `JEV_BASE_URL`. No production code consults a fixture.

**External contracts that must not break**

- `.local/sentinel.jsonl` and `.local/compact.jsonl` row keys; `SENTINEL_VERSION` `shadow-v4` (`scope_sentinel.py:20`), `ADVISOR_VERSION` `advisor-v1` (`compact_advisor.py:26`), `ROUTER_VERSION` `balanced-shards-v2` (`skill_router.py:28`). Issue #17 reads the sentinel rows.
- Hook argv shapes `hook [host] [--user]` and `judge <log> <host>` (`scope_sentinel.py:546-554`, `compact_advisor.py:235-240`); the three project configs and `install_user.py:24-28` call them.
- `ask_jev_files.py` exit codes 0 / 2 / 64 / 78 and the JSON error envelope (`:8`, `:196-198`, `:230-231`, `:463-466`); the `skipped` reason `jev: <first stderr line>` pinned by `tests/test_ask_jev_files.py:165-170`.
- `handoff_check.py` CLI flags (`:242-248`), exit codes 0 / 1 / 2, and the sanitised error line `inspect provider access and limits locally` pinned by `tests/test_handoff_check.py:211-221`; `get_isolated_env()` as a module attribute raising on a missing key (`tests/test_handoff_check.py:87-111`).
- `fixture_curator.py` output lines (`Evaluating i/n: id... OK|FLAGGED|ERROR: …`, `Completed in …`, `Flagged …; N failed.`) and exit codes pinned by `tests/test_fixture_curator.py:100-110`.
- `skill_router.suggest()` return keys and the two-request contract pinned by `tests/test_router.py:72-90`, including `input_tokens` summed across requests.
- `JEV_BIN`, `JEV_MODEL`, `JEV_BASE_URL`, `JEV_LOG_DIR`, `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` environment variables keep their meaning (`README.md:9`).
- Hook stdout stays empty in shadow mode and the PreToolUse hook returns in under 2 s (`tests/test_sentinel.py:99-104,240`).
- Every `tests/test_*.py` runs green via `python3 tests/<name>.py` (baseline: all ten pass on `main` at `88a781d`, run 2026-10-16).

## 3. Root Cause Analysis

### D1 — Six copies of the Jev subprocess call *(high)*
- Symptom: the same transport bug or hardening must be applied in six places; three error policies coexist (stderr hidden in five callers, surfaced in one; timeout caught in two).
- Mechanism: each module owns its own `subprocess.run` of `jev`, key check, model resolution, and exit handling (`scope_sentinel.py:232-253`, `ask_jev_files.py:159-179`, `compact_advisor.py:143-172`, `skill_router.py:279-302`, `fixture_curator.py:67-93`, `handoff_check.py:142-200`). Nothing in the repo exports a call function; `ask_jev_files.py:24-35` and `compact_advisor.py:14-24` import only constants from the sentinel.
- Evidence: `grep -c 'subprocess.run' *.py` on 2026-10-16 finds a `jev` invocation in all six files; the timeout catch exists only at `ask_jev_files.py:170-171` and `handoff_check.py:185-186`.

### D2 — Response validation differs per caller *(medium)*
- Symptom: a zero-exit `jev` whose stdout is JSON without `answers` crashes `ask_jev_files.py files` with a traceback (exit 1, stdout not JSON) while `handoff_check.py` reports `Jev response missing 'answers' object`.
- Mechanism: `ask_jev_files.py:244-247` wraps only `jev_call` in `try`; `:256` indexes `response["answers"]` outside it, and `cmd_ask` does the same at `:450`. `handoff_check.py:194-220` checks envelope, per-item presence, and verdict; `fixture_curator.py:94` and `scope_sentinel.py:259,277` rely on `KeyError`.
- Evidence: the `files` worker returns `(rel, response, None, True)` at `:245` for any dict; the `KeyError` at `:256` is raised in the main thread inside `pool.map` iteration with no handler.

### D3 — Environment isolation exists only in `handoff_check.py` *(medium)*
- Symptom: five of six callers run `jev` (a bash script that execs `curl` and `jq`) with the full parent environment. In a Claude session that environment carries `GH_TOKEN`, `DISCORD_BOT_TOKEN`, and `RUNPOD_API_KEY` (`/home/alex/AGENTS.md`, Secrets section).
- Mechanism: `handoff_check.py:69-84` builds `{PATH, HOME, USER, SYSTEMROOT, TMPDIR}` plus one Jev key plus `JEV_MODEL` and passes it at `:182`; `scope_sentinel.py:240-247`, `ask_jev_files.py:162-169`, `compact_advisor.py:150-165`, `skill_router.py:287-294`, `fixture_curator.py:79-86` pass no `env=`. `with_jev_key.sh:3-7` only adds the key.
- Evidence: `tests/test_handoff_check.py:87-98` asserts `GH_TOKEN` is absent from the handoff env; no other test asserts anything about the child environment because no other caller controls it.

### D4 — `input_tokens` has two readers *(low)*
- Symptom: a response carrying `"usage": null` would raise `AttributeError` in two callers and read 0 in four.
- Mechanism: `scope_sentinel.py:268,289` and `skill_router.py:305-306` call `.get("usage", {})`, which returns `None` for an explicit null; `compact_advisor.py:215-217`, `fixture_curator.py:99`, `handoff_check.py:231-232` use `(… or {})`.
- Evidence: the divergence itself; no provider response with `usage: null` has been observed (every live row to date carries an integer). The stub at `tests/test_fixture_curator.py:79` sends `{"input_tokens": None}` and the curator reads 0.

### D5 — Levels 3 and 5 exist only ad hoc *(low)*
- Symptom: a new router (issue #28, agy host) would copy `skill_router.py:309-379` wholesale, including the transport (D1).
- Mechanism: the composite gate average (`skill_router.py:321-325`), its threshold (`:339`), and the fits floor (`:365-369`) are inline in `suggest`; no document in the repo maps the ten-levels patterns to the code that embodies them.
- Evidence: `grep -rn 'Level 3\|composite\|Level 5' README.md docs/` returns nothing on 2026-10-16. No runtime symptom today.

## 4. Design Constraints

**Established empirically** (how observed, what invalidates)

| Fact | Observed by | Invalidated by |
|---|---|---|
| `jev` accepts `-m -q -j -n -c -s -h`; `-n` prints the request body and the route without a key; a failed `curl` prints the response body to stderr and exits 2; no key exits 78 | `~/.local/bin/jev:45,99,101-104`; `jev -n` run 2026-10-16 (route `https://openrouter.ai/api/v1/systemone` for the key on this box) | a new `jev` script |
| `jev` needs only `PATH` (for `curl`, `jq`), the key, and optionally `JEV_BASE_URL`; it never reads `JEV_MODEL` (`grep -c JEV_MODEL ~/.local/bin/jev` prints 0; the model arrives only through `-m`, `jev:44,50`), so `handoff_check.py:81-82` forwards a variable the child ignores; `curl` and `jq` are at `/usr/bin` | `jev:44,50,86-95`; `command -v jq`, `ls /usr/bin/curl` 2026-10-16; `tests/test_router.py:55-61` passes `JEV_BASE_URL` through the environment | `jev` reading a new variable |
| No proxy or CA variable is set in this session (`HTTPS_PROXY`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `NO_PROXY` all unset) | `env | grep -iE 'proxy|ca_bundle|ssl_cert|curl_ca'` empty, 2026-10-16 | a shell profile or host exporting one |
| `curl` inside `jev` times out at 30 s (`-m 30`), below every caller's 40 s | `jev:101` | `jev` raising `-m` |
| All ten `tests/test_*.py` pass on `main` `88a781d` with Python 3.12.3 | `for t in tests/test_*.py; do python3 "$t"; done`, 2026-10-16 | a failing baseline |
| Four test files import a migrated module in-process without the repo root on `sys.path`: `tests/test_sentinel.py:138-141` and `:162-167` (two loaders in one file), `tests/test_router.py:11-14`, `tests/test_fixture_curator.py:13-17`, `tests/test_handoff_check.py:15-19`; two already insert it (`tests/test_ask_jev_files.py:113`, `tests/test_compact.py:11`) | reading the loaders | a test runner that sets `PYTHONPATH` |
| Codex trusts a hook by hashing the hook definition, not the script it runs, so editing a script needs no re-trust | `docs/specs/ten-levels-port.md:131` and Phase 1 of that spec (shipped, PR #30, no re-trust needed) | Codex changing the key scheme |
| User-scope hooks run the primary checkout `/home/alex/JevDev` by absolute path, so a module added beside `scope_sentinel.py` is importable there once pulled | `install_user.py:24-28`; `README.md:140-146` | a copy-based installer |

**Imposed**

- Python 3 standard library only; `jev` is `~/.local/bin/jev` and never a pip package (user, settled).
- Tests are plain-assert `tests/test_jev_patterns.py` with a stub `jev` on `JEV_BIN`, the harness of `tests/test_sentinel.py` (user, settled).
- One live smoke per phase via `smoke.sh` (user, settled); the router phase adds one `route` call because `smoke.sh` has no router feature (`smoke.sh:3`).
- No new host hooks; hook behaviour stays shadow-only (user, settled).
- `SENTINEL_VERSION` bumps only if a row key changes; no row key changes here, so it stays `shadow-v4` (user, settled).
- Every existing `tests/test_*.py` keeps passing unchanged in meaning: loader lines may be added, assertions may not change (user, settled).
- All six callers migrate in this spec (DR-1, decided at the Phase 2 gate).
- `ten-levels-port.md` GC2 ("every Jev call is `subprocess.run([JEV, …])` exactly as `scope_sentinel.py`") is superseded by GC2 below: the one place that pattern lives is `jev_patterns.call`.
- Worktree on a feature branch, one PR per phase, merged from the primary checkout (`AGENTS.md`); never commit `.local/`, `transcripts/`, or keys.

### Global constraints

- GC1: Python ≥ 3.12 (3.12.3 here), standard library only; no new third-party import in any file this spec touches.
- GC2: After Phase 4, `jev_patterns.call` is the only `subprocess.run` of `jev` in the repo: `grep -n '"-j"' *.py` prints exactly one line and it is in `jev_patterns.py` (today it prints six: `scope_sentinel.py:241`, `ask_jev_files.py:163`, `compact_advisor.py:157`, `skill_router.py:288`, `fixture_curator.py:80`, `handoff_check.py:176`; `str(JEV)` would miss the handoff, which names its variable `target_bin`). Until then, a migrated caller has no `"-j"` literal left.
- GC3: Every `call` runs `[str(JEV), "-m", <model>, "-q", json.dumps(questions), "-j", <job>]` with the state on stdin (a `str` verbatim, anything else `json.dumps`-encoded), `capture_output=True, text=True, check=False, start_new_session=True`, default timeout 40 s.
- GC4: The child environment of every `call` is exactly: `PATH`, `HOME`, `USER`, `SYSTEMROOT`, `TMPDIR`, `JEV_BASE_URL` (each only if set in the parent; `JEV_MODEL` is read by `model_name()` in the parent and travels as `-m`, never as an environment variable) plus `TYPESAFE_API_KEY` when it is non-empty, else `OPENROUTER_API_KEY` when it is non-empty. Nothing else. Key presence is truthiness everywhere (`has_key()` and `isolated_env()` agree); `handoff_check.py:74-77` tests membership, which forwards an empty `TYPESAFE_API_KEY` and drops a set `OPENROUTER_API_KEY`, and is not carried over.
- GC5: `str(JevError)` never contains `jev`'s stderr; stderr is reachable only as `JevError.stderr` (first non-empty line, at most 200 characters). The only caller that emits it is `ask_jev_files.py`, through `scope_sentinel.redact`.
- GC6: `JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")`, `DEFAULT_MODEL = "jev-latest"`, `NO_KEY = "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"` are defined once, in `jev_patterns.py`, at import time.
- GC7: No row key in `sentinel.jsonl` or `compact.jsonl` is renamed or removed; `SENTINEL_VERSION`, `ADVISOR_VERSION`, `ROUTER_VERSION` are unchanged.
- GC8: Every pre-existing `tests/test_*.py` passes; the only permitted edits to one are a single `sys.path.insert(0, <repo root>)` line in its module loader and adding `"jev_patterns.py"` to a fixture that copies a migrated module into a temp repo (`tests/test_check_install.py` `make_root`, user-confirmed 2026-10-20). Assertions never change.
- GC9: No hook emits `permissionDecision`, `decision`, or `updatedInput`; hook stdout stays empty in shadow mode.
- GC10: No PR adds a file under `.local/` or `transcripts/`, or a string matching `scope_sentinel.SECRETS` outside `tests/`. Under `tests/`, only made-up placeholder values like AC-1.2's `Bearer secret_leaked_key` are allowed.
- GC11: One PR per phase from a worktree on `feat/jev-patterns-p<n>-<slug>` off `main`; each PR body carries the test command last lines and the phase's live smoke line.

## 5. Target Design

### 5.1 `jev_patterns.py` (new, stdlib only)

```python
JEV: Path                     # os.environ["JEV_BIN"] or ~/.local/bin/jev, resolved at import
DEFAULT_MODEL = "jev-latest"
DEFAULT_TIMEOUT = 40.0
NO_KEY = "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"
SAFE_ENV = ("PATH", "HOME", "USER", "SYSTEMROOT", "TMPDIR", "JEV_BASE_URL")

class JevError(RuntimeError):
    returncode: int | None    # jev's exit status; None for OSError, timeout, bad JSON, missing answer
    stderr: str               # first non-empty stderr line, clipped to 200 chars; "" when none
    # str(error) is the safe message and never includes stderr (GC5)

def has_key() -> bool
def model_name(model: str | None = None) -> str
def isolated_env() -> dict[str, str]
def input_tokens(response: dict) -> int
def call(state, questions: dict, *, job: str, model: str | None = None,
         timeout: float = DEFAULT_TIMEOUT) -> dict
```

`call` contract, in order:

1. `env = isolated_env()`: the GC4 allow-list; the key is `TYPESAFE_API_KEY` when non-empty, else `OPENROUTER_API_KEY` when non-empty; raises `JevError(NO_KEY)` (`returncode=None`) before any subprocess when neither is non-empty (the same truthiness test as `has_key()`).
2. `stdin = state if isinstance(state, str) else json.dumps(state)`.
3. `subprocess.run([str(JEV), "-m", model_name(model), "-q", json.dumps(questions), "-j", job], input=stdin, capture_output=True, text=True, timeout=timeout, env=env, start_new_session=True, check=False)` timed with `time.perf_counter()`.
4. `OSError` (missing or non-executable binary) → `JevError(f"{type(e).__name__}: {e}")`. `subprocess.TimeoutExpired` → `JevError(f"jev timed out after {timeout:g}s")`.
5. Non-zero exit → `JevError(f"jev exited {rc}; inspect provider access and limits locally", returncode=rc, stderr=<first non-empty stderr line>[:200])`.
6. `json.loads(stdout)` raising `ValueError` (a `JSONDecodeError`, or an integer literal over Python's 4300-digit limit) or `RecursionError` → `JevError("jev returned non-JSON output")`; a non-dict → `JevError("jev response is not an object")`.
7. `response.get("answers")` not a dict → `JevError("jev response missing 'answers' object")`; for every id in `questions`, `answers[id]` absent or not a dict → `JevError(f"jev response missing answer {id!r}")`. Nothing else is validated (DR-5).
8. `response["elapsed"] = <seconds around step 3>`; return `response`.

`call` does not validate the questions object (option counts, score levels, token budget): internal question sets are module constants, and the only user-supplied questions are validated at that boundary by `ask_jev_files.py:128-149`, which stays where it is. `call` makes exactly one attempt. It does not retry on 429 / 5xx: the upstream client retries three times with backoff inside a 30 s budget (`/tmp/ten-levels-src/apps/ten-levels/src/core/client.ts:33-35,56-58`), but here `jev` already spends up to 30 s in one `curl` (`jev:101`), the PreToolUse hook has a 10 s host timeout and the Stop hook 45 s (`.claude/settings.json:24,45`), and no caller retries today; the CLI's consumer (the agent) retries on the `jev: HTTP 429 …` reason it is shown (DR-2).

`model_name(model)` returns `model or os.environ.get("JEV_MODEL") or DEFAULT_MODEL`. `has_key()` is `bool(os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))`. `input_tokens(response)` is `int((response.get("usage") or {}).get("input_tokens") or 0)`.

What the module does not contain, and why (DR-2): `decide`, `choose`, `score`, `gate`, `route` from the brief's candidate list. Each would have zero or one caller after migration; the level 1 to 5 patterns are documented in the README against the code that already embodies them.

### 5.2 Callers after migration

| Caller | Replaces | Keeps | Closes |
|---|---|---|---|
| `scope_sentinel.py` | `run_jev` (`:232-253`), `DEFAULT_MODEL` / `JEV` (`:18-19`), the two `usage` reads (`:268,289`), the model read at `:498` | `judge_write`, `judge_bash`, gates, thresholds, rows, `run_hook` / `run_judge`, the manual CLI | D1, D3, D4 |
| `ask_jev_files.py` | `jev_call` (`:159-179`), `has_key` / `model_of` (`:201-208`), `NO_KEY` (`:60-62`), the `DEFAULT_MODEL, JEV` imports (`:27-28`) | subcommands, exit codes, `validate_questions`, the live gate, the `skipped` reason format (now `f"jev: {redact(e.stderr) or e}"`) | D1, D2, D3 |
| `compact_advisor.py` | `ask_jev` (`:143-172`), `import subprocess` (`:10`), the `DEFAULT_MODEL, JEV` imports (`:15-16`), the model read at `:181` | `decide_tier`, `tier_message`, rows, `run_hook` error formatting (`:228-231`, unchanged: `JevError` is a `RuntimeError`, so the row gets the safe message with no type prefix) | D1, D3 |
| `skill_router.py` | the body of `jev()` (`:279-302`), `usage_tokens` (`:305-306`), `JEV` / `DEFAULT_MODEL` (`:26-27`), the model fallback at `:328` | `jev(questions, request) -> tuple[dict, float]` as a two-line wrapper that builds the router state and returns `(response, response["elapsed"])`; `suggest`, the gate average, thresholds, hook and CLI handlers (`:885` keeps `subprocess.TimeoutExpired` for the claude/codex arms at `:478-484,536-541`) | D1, D3, D4 |
| `fixture_curator.py` | the body of `curate_with_jev` (`:67-100`), `DEFAULT_MODEL` / `JEV` (`:18-19`), `import subprocess`, `import os`, `import time` (`:12,14,16`, no other use) | `curate_with_jev(record) -> dict` signature and return keys; `score()` strictness (`:59-64`); output lines | D1, D3 |
| `handoff_check.py` | `resolve_jev_binary` (`:63-66`), `get_isolated_env` (`:69-84`, re-exported from the library under the same name), `DEFAULT_MODEL` / `DEFAULT_TIMEOUT` (`:18-19`, `DEFAULT_TIMEOUT` imported from the library), the `jev_bin` parameter (`:147`, no caller), the subprocess and envelope checks (`:156-204`, `:209-210`), `import subprocess`, `import time`, `import os` (`:11,14,16`) | `evaluate_handoff(items, handoff, model=None, timeout=DEFAULT_TIMEOUT) -> HandoffReport`; verdict and confidence checks (`:212-229`); CLI flags and exit codes | D1, D2 |

README gains a `## Jev from code` section (Phase 4) that names, per level, the in-repo code that embodies it: level 1 `compact_advisor.decide_tier` (one noul, one `>`), level 2 `scope_sentinel.BASH_QUESTIONS` + `gate_bash` (two picks, one call), level 3 `skill_router.suggest` gate average with the weights readable at `:321-325`, level 4 `gate_bash` confidence thresholds `BASH_THRESHOLDS`, level 5 `skill_router.suggest` two-request routing. It closes D5 by giving the next author a map instead of a function to copy.

### 5.3 Error model after the change

| Event | `JevError` message (`str`) | `.returncode` | `.stderr` | Sentinel row `error` | Compact row `error` | `ask_jev_files` output |
|---|---|---|---|---|---|---|
| no key | `NO_KEY` text | `None` | `""` | `JevError: Jev key unavailable…` | `Jev key unavailable…` | `{"error": NO_KEY}` exit 78 (checked by `has_key()` before any call, as today) |
| `jev` exit 2 with stderr `Fatal … Bearer secret` | `jev exited 2; inspect provider access and limits locally` | 2 | `Fatal … Bearer secret` | `JevError: jev exited 2; …` | `jev exited 2; …` | `skipped` reason / `error` `jev: Fatal … Bearer [REDACTED]` |
| timeout | `jev timed out after 40s` | `None` | `""` | `JevError: jev timed out after 40s` | `jev timed out after 40s` | `jev: jev timed out after 40s` |
| non-JSON stdout | `jev returned non-JSON output` | `None` | `""` | same pattern | same | `jev: jev returned non-JSON output` |
| `answers` missing or an id missing | `jev response missing answer 'effect'` | `None` | `""` | same pattern | same | `jev: jev response missing answer 'relevant'` |

The sentinel row prefix changes from `RuntimeError:` to `JevError:` for transport failures (`scope_sentinel.py:524` formats the type name); the row key set is unchanged (GC7). In `ask_jev_files.py`, `pick` and the `--command` gate print the same redacted line after their own prefixes (`pick failed: `, `gate failed, command not run: `).

## 6. Decision Records

### DR-1: Migrate all six callers in this spec
- Decision: the library ships in Phase 1 together with its first caller, and Phases 2 to 4 move the other five; no caller keeps a private subprocess.
- Context: D1; the brief left this open; `fixture_curator.py` and `handoff_check.py` were not in the brief.
- Rationale: a library with zero callers is a seventh copy and D1 stays open; a library with one caller leaves five error policies live. Each caller already has an offline test with a stub `jev` and a smoke path, so each migration gates itself.
- Alternatives considered:
  - Ship the library only, migrate in a follow-up — rejected: nothing forces the follow-up; `ten-levels-port.md` GC2 would still bless the copy pattern.
  - Migrate only the four callers the brief named — rejected: the two unnamed ones are the hardened one (`handoff_check.py`, whose policy the library adopts) and the plain-string one (`fixture_curator.py`, which proves the `str` state path).
  - Leave it as is — rejected: issue #28 copies `skill_router.py:279-302` next.
- Consequences: four PRs instead of one; three test loaders gain a `sys.path` line (GC8); the user-scope checkout must be pulled after each merge (existing rule, `README.md:145`).

### DR-2: API is `call` + `JevError` + four helpers; the level 1 to 5 helper functions are not ported
- Decision: export `call`, `JevError`, `has_key`, `model_name`, `isolated_env`, `input_tokens`, and the constants `JEV`, `DEFAULT_MODEL`, `DEFAULT_TIMEOUT`, `NO_KEY`, `SAFE_ENV`. Do not export `decide`, `choose`, `score`, `gate`, or `route`. Document levels 1 to 5 in the README against existing code.
- Context: the brief asked to evaluate, not assume, that candidate list, with "drop anything with one caller". Counted after migration: `decide(prob, threshold)` would replace a `>=` in `gate_bash` / `gate_write` and a `>` in `decide_tier` (`compact_advisor.py:112-116`), so one helper cannot serve both without a flag; `choose` is `answers[id]["choice"]`; `score(answers, weights)` has one caller (`skill_router.py:321-325`, an inverted-sign average that does not fit a weights dict); `gate` three-way has zero callers (`gate_bash` and `gate_write` are two-way and stay until issue #17 step 5); `route` has zero callers (the sharded two-request router does not fit `route(state, routes)`).
- Rationale: one-caller helpers hide the comparison that *is* the pattern; the upstream level files are 25 to 55 lines because the client is the shared part (`apps/ten-levels/src/levels/level01/urgency-gate.ts:15-24`, `level04/shell-command-gate.ts:35-55`).
- Alternatives considered:
  - Port all five helpers verbatim — rejected: four of five would have no caller; `gate` would carry the upstream 0.5 / 0.9 thresholds (`level04/confidence.ts:5-8`) that issue #17 is meant to calibrate, not import.
  - Port the upstream client including its retry/backoff (`core/client.ts:33-35,56-58`: three attempts on 429 / 502 / 503 / 529 inside 30 s) — rejected: the decisive blocker is the hook budget; the PreToolUse hook is killed by the host at 10 s and the Stop hook at 45 s (`.claude/settings.json:24,45`), and one `jev` attempt already runs `curl -m 30` (`jev:101`), so a second attempt can never complete inside either budget. The CLI consumer is an agent that sees the `jev: HTTP 429 …` reason and can retry itself.
  - A `JevClient` class with methods per level — rejected: six callers need one function; a class adds a construction step to every hook.
  - Leave it as is — rejected: D1.
- Consequences: the brief's "ports levels 1 to 5 as helpers" is narrowed to "ports the client and documents the levels" — the headline judgment call of this spec, recorded here and in the PR body; a future caller that needs three-way gating adds `gate` with its first caller.

### DR-3: `str(JevError)` is the safe message; stderr is opt-in and only `ask_jev_files.py` emits it, redacted
- Decision: the message is `jev exited N; inspect provider access and limits locally`; `.stderr` carries the first non-empty line (≤ 200 chars); `ask_jev_files.py` formats `f"jev: {redact(e.stderr) or e}"`.
- Context: `tests/test_handoff_check.py:211-221` asserts a stderr secret never reaches stdout or stderr; `tests/test_ask_jev_files.py:165-170` asserts the `files` skip reason is `jev: HTTP 429 rate limited`; `jev:101-104` prints provider error bodies, which can quote the request text (`skill_router.py:297-298` comment).
- Rationale: the hooks and the curator never show output to a human at the moment of failure, so the safe message loses nothing; the CLI's consumer is the agent that composed the request, and the first line of a provider error is what it needs to retry.
- Alternatives considered:
  - Surface stderr by default — rejected: breaks `tests/test_handoff_check.py:219-220` and leaks provider bodies into hook logs.
  - Never keep stderr — rejected: breaks `tests/test_ask_jev_files.py:168-170` and removes the 429 signal from the CLI.
  - Redact inside the library — rejected: `jev_patterns` cannot import `scope_sentinel` (the sentinel imports it); the one emitter already imports `redact`.
- Consequences: `ask_jev_files` output can carry a provider error line (redacted); row `error` strings lose the per-exception type variety for transport failures.

### DR-4: One isolated environment and `start_new_session=True` for every call, with `JEV_BASE_URL` added to the allow-list
- Decision: `isolated_env()` is `handoff_check.get_isolated_env` (`:69-84`) plus `JEV_BASE_URL`, minus `JEV_MODEL` (`jev` never reads it, §4), with the key chosen by truthiness (GC4); every `call` uses it and `start_new_session=True` (`handoff_check.py:181`).
- Context: D3; `tests/test_router.py:60` routes the real `jev` to a local server via `JEV_BASE_URL`; `jev:95` reads it.
- Rationale: one policy is the point of the library; the hooks are where the richest environment leaks (`/home/alex/AGENTS.md` Secrets); `jev` needs nothing beyond GC4 (`jev:86-95`, `/usr/bin/curl`, `/usr/bin/jq`).
- Alternatives considered:
  - An `env=` parameter defaulting to inherit — rejected: five callers would default to the leaky path; the hardening stays one caller's property.
  - Inherit everything (status quo) — rejected: D3.
  - Keep `start_new_session` only for `handoff_check` — rejected: a per-caller flag for a property with no observed downside; the sentinel judge already runs in its own session (`scope_sentinel.py:487`).
- Consequences: a proxy or CA variable in the parent environment is dropped (none set here; §10); a Ctrl-C in a CLI no longer reaches the `jev` child, which ends on its own within `curl -m 30`.

### DR-5: Presence-only response validation
- Decision: `call` checks that `answers` is a dict and that every question id maps to a dict. It does not check `type`, value ranges, NaN, or `probabilities`.
- Context: D2; `tests/test_fixture_curator.py:71-74` sends `NaN` and `{"error": "x"}` answers and expects the curator's own `score()` to fail them (`:107,110`); `tests/test_router.py:33-44` and `tests/test_handoff_check.py:119-127` send answers without `type`.
- Rationale: the callers' policy readers are the right place for domain checks (the curator wants a range error, the handoff wants a verdict enum); the library only guarantees the shape every caller indexes.
- Alternatives considered:
  - Upstream-strict validation (`type` per question, ranges, legend) — rejected: fails four existing stubs; duplicates `fixture_curator.score` and `handoff_check.py:213-227`.
  - No validation (status quo) — rejected: D2's traceback in `files`.
- Consequences: a wrong-typed answer still surfaces as a `KeyError` in the caller (unchanged behaviour, visible in rows and `pick failed:` errors).

### DR-6: `elapsed` is added to the returned response dict
- Decision: `call` returns the parsed response with one extra key, `elapsed` (float seconds around the subprocess), instead of a tuple.
- Context: three callers return `(response, elapsed)` today (`scope_sentinel.py:253`, `compact_advisor.py:172`, `skill_router.py:302`), three return derived dicts.
- Rationale: no caller forwards the whole response anywhere (`ask_jev_files.py:457-458` and `compact_advisor.py:214` pick `usage` and `model`), so the key cannot leak into an output contract; one return type keeps `call(...)["answers"]` a one-liner for the CLI.
- Alternatives considered:
  - Return `(response, elapsed)` — rejected: every CLI call site unpacks a value it discards.
  - Drop `elapsed` and let callers time it — rejected: five callers log it; timing inside the library is the only way the number means the same thing everywhere.
- Consequences: `elapsed` is not a provider field; a future consumer that dumps the full response will see it.

### DR-7: `JEV` resolves at import time; `handoff_check`'s call-time resolution and `jev_bin` parameter are dropped
- Decision: `jev_patterns.JEV` is computed once at import (GC6), as four modules already do; `evaluate_handoff` loses `jev_bin`.
- Context: `handoff_check.py:63-66` resolves per call and `:158-159` pre-checks executability; no caller or test passes `jev_bin` (grep 2026-10-16).
- Rationale: four of six modules already bind `JEV` at import and every subprocess-driven test sets `JEV_BIN` in the child's environment, so the policy is the repo's existing one; the two in-process tests that import a migrated module without `JEV_BIN` (`tests/test_compact.py:12-13`, `tests/test_router.py:11-14` before `:59-61`) never call Jev through that binding (the advisor test runs the hook as a subprocess; the router test routes the real script by `JEV_BASE_URL`). A missing binary becomes `JevError("FileNotFoundError: …")` from `subprocess.run` with the same exit path as today.
- Alternatives considered:
  - Resolve per call — rejected: a module constant is what five of six callers expect and what `tests/test_ask_jev_files.py:112` relies on.
  - Keep `jev_bin` as a pass-through — rejected: one-caller parameter with zero callers.
- Consequences: a test that imports `jev_patterns` must set `JEV_BIN` first (noted in `tests/test_jev_patterns.py`).

### DR-8: Phase order is sentinel, CLI, advisor, then the three CLIs; the sentinel is the tracer bullet
- Decision: Phase 1 = library + tests + `scope_sentinel.py`; Phase 2 = `ask_jev_files.py`; Phase 3 = `compact_advisor.py`; Phase 4 = `skill_router.py`, `fixture_curator.py`, `handoff_check.py`, README levels section.
- Context: `scope_sentinel.py` has the strictest test (`tests/test_sentinel.py`, 2 s bound, error rows, judge cap) and the simplest smoke (`smoke.sh claude bash`); `ask_jev_files.py` carries the only stderr-surfacing contract (DR-3) and the D2 crash; the advisor is a synchronous Stop hook; the three CLIs have no shared user-facing path.
- Rationale: the highest-severity, best-tested caller proves the library end to end before the error-policy change (DR-3) is exercised by the CLI.
- Alternatives considered:
  - One PR for everything — rejected: a review cannot gate six migrations at once; a failing smoke in one caller blocks all.
  - Library-only Phase 1 — rejected: DR-1.
- Consequences: between Phases 1 and 4 two transports coexist; GC2's grep check holds only after Phase 4.

## 7. Implementation Plan

### File manifest

| Action | Path | Responsibility | Phase |
|---|---|---|---|
| Create | `docs/specs/jev-patterns-library.md` | this spec | spec PR |
| Create | `jev_patterns.py` | the §5.1 module | 1 |
| Create | `tests/test_jev_patterns.py` | stub-`jev` tests for every `call` branch and helper | 1 |
| Modify | `scope_sentinel.py` | delete `run_jev`, `DEFAULT_MODEL`, `JEV`; call the library in `judge_write`, `judge_bash`, `run_judge` | 1 |
| Modify | `tests/test_sentinel.py` | one module-level `sys.path.insert` line after `SOURCE` (`:11`), serving both in-process loaders (`:138-141`, `:162-167`) | 1 |
| Modify | `tests/test_check_install.py` | add `"jev_patterns.py"` to the `make_root` copy list: its temp repo runs `ask_jev_files.py --help`, which now imports the library | 1 |
| Modify | `ask_jev_files.py` | Phase 1: import `DEFAULT_MODEL, JEV` from `jev_patterns`; Phase 2: delete `jev_call`, `has_key`, `model_of`, `NO_KEY`; call the library | 1, 2 |
| Modify | `compact_advisor.py` | Phase 1: import `DEFAULT_MODEL, JEV` from `jev_patterns`; Phase 3: delete `ask_jev`; call the library | 1, 3 |
| Modify | `README.md` | Phase 1: library paragraph and test command; Phase 4: `## Jev from code` section | 1, 4 |
| Modify | `skill_router.py` | `jev()` becomes a wrapper over the library; delete `usage_tokens`, `JEV`, `DEFAULT_MODEL` | 4 |
| Modify | `fixture_curator.py` | `curate_with_jev` calls the library; delete constants and dead imports | 4 |
| Modify | `handoff_check.py` | `evaluate_handoff` calls the library; delete `resolve_jev_binary`, `get_isolated_env`, `jev_bin`, envelope checks | 4 |
| Modify | `tests/test_router.py` | one `sys.path.insert` line before `:12` | 4 |
| Modify | `tests/test_fixture_curator.py` | one `sys.path.insert` line in `load_module` (`:13-17`) | 4 |
| Modify | `tests/test_handoff_check.py` | one `sys.path.insert` line in `load_module` (`:15-19`) | 4 |

`ask_jev_files.py`, `compact_advisor.py`, and `README.md` are shared by design (Phase 1 touches one import list or one paragraph; the owning phase does the migration). Every other entry has exactly one owning phase.

### Phase 1 — `jev_patterns.py` and `scope_sentinel.py` (tracer bullet)
- Outcome: the sentinel's bash and write judges reach Jev only through `jev_patterns.call`, with the isolated environment, and every sentinel test and the Claude bash smoke pass.
- Changes:
  - Create: `jev_patterns.py` — §5.1 verbatim: constants, `JevError`, `has_key`, `model_name`, `isolated_env`, `input_tokens`, `call`. Module docstring states GC3 to GC6. No `__main__`.
  - Create: `tests/test_jev_patterns.py` — sets `JEV_BIN` to a tmp stub before importing (DR-7); the stub records `argv`, `stdin`, and `dict(os.environ)` to a JSON file and answers from a `cfg.json` (exit code, stderr text, sleep, stdout override), the pattern of `tests/test_sentinel.py:27-57`.
  - Modify: `scope_sentinel.py:18-19` — delete `DEFAULT_MODEL` and `JEV`; add `from jev_patterns import call, input_tokens, model_name`.
  - Modify: `scope_sentinel.py:232-253` — delete `run_jev`.
  - Modify: `scope_sentinel.py:258-269` — `response = call({"path": rel_path, "content": content}, WRITE_QUESTIONS, job="scope_sentinel")`; `"elapsed": response["elapsed"]`; `"input_tokens": input_tokens(response)`.
  - Modify: `scope_sentinel.py:276-290` — `response = call(state, {"scope": SCOPE_QUESTION, **BASH_QUESTIONS}, job="scope_sentinel")`; same two substitutions.
  - Modify: `scope_sentinel.py:498` — `"model": model_name()`.
  - Modify: `ask_jev_files.py:24-35` — remove `DEFAULT_MODEL` and `JEV` from the `scope_sentinel` import; add `from jev_patterns import DEFAULT_MODEL, JEV`. No other change.
  - Modify: `compact_advisor.py:14-24` — same two-name move. No other change.
  - Modify: `tests/test_sentinel.py:11` — insert `sys.path.insert(0, str(SOURCE.parent))` at module level right after `SOURCE` is defined. The file has two in-process loaders (`check_patterns` `:138-141` and `load_sentinel` `:162-167`); a module-level line serves both regardless of run order.
  - Modify: `README.md` — after the Scope Sentinel test block (`:68-70`), a paragraph: `jev_patterns.py` is the only Jev transport; `call(state, questions, job=…)`; isolated env; `JevError`; `python3 tests/test_jev_patterns.py`.
  - Test: `tests/test_jev_patterns.py`, `tests/test_sentinel.py`.
- Interfaces:
  - Consumes: `subprocess`, `json`, `os`, `time`, `pathlib` (stdlib). From `scope_sentinel`: nothing (the dependency points the other way).
  - Produces (import path `jev_patterns`): everything in §5.1 with the `call` contract steps 1 to 8; `JevError(message, *, returncode=None, stderr="")`; `isolated_env()` raising `JevError(NO_KEY)`; `model_name(None)` reading `JEV_MODEL` at call time; `input_tokens({})` → 0. Invariant: `call` never prints and never raises anything but `JevError` for transport or envelope failures (`TypeError` from a non-serialisable `state` propagates as today's `json.dumps` would).
  - Unchanged: sentinel row keys and `SENTINEL_VERSION` `shadow-v4`; argv shapes `hook [host] [--user]` / `judge <log> <host>`; the manual CLI; `import subprocess` stays in `scope_sentinel.py` for the detached judge (`:482-488`); `ask_jev_files.py` and `compact_advisor.py` behaviour (import move only).
- Gotchas: `tests/test_sentinel.py:84-90` passes the whole `os.environ` plus `JEV_BIN` and `TYPESAFE_API_KEY`; with GC4 the stub no longer sees `JEV_BIN`, which it never read. The stub is `#!/usr/bin/env python3`, so `PATH` must stay in the allow-list. `run_judge` formats errors with the type name (`:524`), so rows now read `JevError: …` — a value change, not a key change (GC7). The hook's `|| true` and `with_jev_key.sh` wrappers are untouched; Codex needs no re-trust (§4).
- Complexity: integration
- Non-goals: migrating the Jev call of any other module; changing thresholds, questions, or rows; `--user` or log paths.
- Depends on: none
- Acceptance criteria:
  - AC-1.1: Given a stub `jev` on `JEV_BIN` that records its argv, stdin, and environment, and `GH_TOKEN=ghp_leak`, `TYPESAFE_API_KEY=k`, `JEV_MODEL=m1`, `JEV_BASE_URL=http://127.0.0.1:1` set in the parent, when `call({"a": 1}, {"q": {"type": "noul", "instructions": "x"}}, job="t")` runs, then the stub's argv is `["-m", "m1", "-q", '{"q": {"type": "noul", "instructions": "x"}}', "-j", "t"]`, its stdin parses to `{"a": 1}`, its environment keys are a subset of `{PATH, HOME, USER, SYSTEMROOT, TMPDIR, JEV_BASE_URL, TYPESAFE_API_KEY}` with `GH_TOKEN` and `JEV_MODEL` absent, the return value carries the stub's `answers` and a float `elapsed`, and `input_tokens` of it equals the stub's `usage.input_tokens`; with a `str` state `"PROMPT: x"` the stdin is exactly that string.
  - AC-1.2: Given the same stub configured to exit 2 after writing `Fatal: Bearer secret_leaked_key` to stderr, when `call` runs, then it raises `JevError` whose `str` is `jev exited 2; inspect provider access and limits locally`, whose `returncode` is 2, whose `stderr` is `Fatal: Bearer secret_leaked_key`, and `secret_leaked_key` is not in `str(error)`; given no key in the environment, or both keys set to the empty string, `call` raises `JevError` with `str` equal to `NO_KEY` and the stub is never executed (no record file); given `TYPESAFE_API_KEY=""` and `OPENROUTER_API_KEY=k2`, the stub's environment has `OPENROUTER_API_KEY` `k2` and no `TYPESAFE_API_KEY`; given a stub that sleeps 3 s and `timeout=0.5`, `JevError` with `str` `jev timed out after 0.5s`; given stdout `not json`, `str` `jev returned non-JSON output`; given stdout `{"answers": {}}` for question id `q`, `str` `jev response missing answer 'q'`; given `JEV_BIN` pointing at a file with mode 0644, `str` starting `PermissionError:`; given `"usage": null`, `input_tokens` returns 0.
  - AC-1.3: Given `tests/test_sentinel.py` with only the `sys.path.insert` line added, when `python3 tests/test_sentinel.py` runs, then it prints `sentinel hook ok` and exits 0, and `git diff --stat main -- tests/test_sentinel.py` shows one insertion and zero deletions.
  - AC-1.4: Given the REC_STUB of `tests/test_sentinel.py` configured to `exit 1`, when the Claude hook receives a `Bash` event, then the row has `gate` `bash`, `error` containing `jev exited 1; inspect provider access and limits locally`, no `effect` key, and the hook exited 0 with empty stdout in under 2 s (GC9); `grep -n 'subprocess.run' scope_sentinel.py` returns exactly one line, the `git rev-parse` call in `repo_root` (today `:168`), and `grep -n '"-j"' scope_sentinel.py` returns nothing (the detached-judge `Popen` at `:482` and the git call are the only subprocess uses left); and every `import`/`from` line of `jev_patterns.py` names a module in `sys.stdlib_module_names` (GC1).
  - AC-1.5: [live] Given the real key loaded by `with_jev_key.sh`, when `bash smoke.sh claude bash` runs in the Phase 1 worktree, then it prints one line with `host=claude`, a non-empty `host_model`, `jev_model` matching `^typesafe/jev-`, `gate=bash`, and no `error=`; the line is pasted into the PR body.

### Phase 2 — `ask_jev_files.py`
- Outcome: the three subcommands call Jev through the library, a malformed zero-exit response is a JSON error instead of a traceback, and provider stderr reaches the agent redacted.
- Changes:
  - Modify: `ask_jev_files.py:24-35` — drop the Phase 1 `from jev_patterns import DEFAULT_MODEL, JEV`; add `from jev_patterns import JevError, NO_KEY, call, has_key, model_name`.
  - Delete: `ask_jev_files.py:60-62` (`NO_KEY`), `:159-179` (`jev_call`), `:201-208` (`has_key`, `model_of`).
  - Modify: `ask_jev_files.py:235,290,376` — `model_of(args)` → `model_name(args.model)`.
  - Modify: `ask_jev_files.py:244-247` — `return rel, call(state, questions, job="ask_jev_files", model=model), None, True` and `except JevError as e: return rel, None, f"jev: {redact(e.stderr) or e}", True`.
  - Modify: `ask_jev_files.py:285-293` — `call({"question": args.q, "files": kept}, questions, job="ask_jev_pick", model=model_name(args.model))["answers"]["pick"]`; the `except (RuntimeError, KeyError)` stays (a `JevError` is a `RuntimeError`) and formats `f"pick failed: {redact(getattr(e, 'stderr', '')) or e}"` (DR-3; added in the #43 review, `getattr` because the handler also catches `KeyError`). `answer["choice"]` sits outside the `try`, so a malformed answer is still a traceback (#44).
  - Modify: `ask_jev_files.py:321-326` — `call({"command": …, "cwd": str(root)}, BASH_QUESTIONS, job="ask_jev_gate", model=model)`.
  - Modify: `ask_jev_files.py:444-447` — `call(state, questions, job="ask_jev", model=model)`; `except JevError as e: return emit({"error": f"jev: {redact(e.stderr) or e}"}, 2)`.
  - Test: `tests/test_ask_jev_files.py` (unchanged; `:113` already inserts the repo root).
- Interfaces:
  - Consumes (from `jev_patterns`): `call(state, questions, *, job, model=None, timeout=40.0) -> dict` raising `JevError` with `.stderr`; `has_key() -> bool`; `model_name(model: str | None) -> str`; `NO_KEY: str`. From `scope_sentinel`: `redact(text: str) -> str` (`:61-64`, already imported at `:33`).
  - Produces: no new symbols. `cmd_files` skip reason and `cmd_ask` error text are `f"jev: {redact(e.stderr) or e}"`; `cmd_pick` and the `--command` gate keep their prefixes (`pick failed: `, `gate failed, command not run: `) followed by `redact(getattr(e, 'stderr', '')) or e`.
  - Unchanged: exit codes 0 / 2 / 64 / 78; `{"error": NO_KEY}` with exit 78 before any file is read (`:230-231`, `:273-274`, `:372-373`); `validate_questions`; the sentinel row written by `gate_command` (`:334-356`); `import subprocess` and `time` stay for `--command` (`:403-413`, `:341`).
- Gotchas: `tests/test_ask_jev_files.py:165-170` expects `jev: HTTP 429 rate limited` from a stub that prints two stderr lines and exits 2 — `.stderr` is the first line, so the text matches only through `e.stderr`, never `str(e)`. The `files` worker runs in a thread pool (`:250`); `JevError` must be caught inside `one()` so a provider failure stays a `skipped` entry.
- Complexity: mechanical
- Non-goals: changing `PICK_FLOOR`, `WORKERS`, token budgets, or the gate.
- Depends on: Phase 1
- Acceptance criteria:
  - AC-2.1: Given the Phase 2 file, when `python3 tests/test_ask_jev_files.py` runs, then it prints `all ask_jev_files checks passed` and exits 0 with `git diff --stat main -- tests/test_ask_jev_files.py` empty.
  - AC-2.2: Given a stub `jev` that exits 0 and prints `{"model": "typesafe/jev-stub-1"}` (no `answers`), when `ask_jev_files.py files -q '{"relevant": {"type": "noul", "instructions": "x"}}' a.txt` runs in a tmp repo containing `a.txt`, then exit code is 0, stdout is one JSON object with `results` `[]` and `skipped` `[{"path": "a.txt", "reason": "jev: jev response missing 'answers' object"}]`, and stderr is empty (no traceback).
  - AC-2.3: Given a stub that exits 2 with stderr `HTTP 401 Authorization: Bearer sk-abcdefghij1234567890 rejected`, when `ask_jev_files.py ask -q '{"ok": {"type": "noul", "instructions": "x"}}' --state hi` runs, then stdout is `{"error": "jev: HTTP 401 Authorization: Bearer [REDACTED] rejected"}` (`scope_sentinel.py:42` keeps the `Authorization: Bearer ` prefix in its capture group; verified by running `redact` on that line, 2026-10-16) and the exit code is 2.
  - AC-2.4: Given `ask_jev_files.py` after this phase, when `grep -nE 'subprocess.run\(\s*$|str\(JEV\)|def jev_call|def has_key|def model_of|^NO_KEY' ask_jev_files.py` runs, then the only `subprocess.run` hit is the `--command` runner at the former `:403` and the other patterns return nothing.
  - AC-2.5: [live] Given the real key, when `bash smoke.sh claude ask` runs in the Phase 2 worktree, then the host's reply names `kind` and `flaky` answers and the printed sentinel row has `host=claude`, `jev_model` matching `^typesafe/jev-`, and `gate=bash`; pasted into the PR body.

### Phase 3 — `compact_advisor.py`
- Outcome: the Stop hook's one Jev call goes through the library; rows and messages are unchanged for every tier and error.
- Changes:
  - Modify: `compact_advisor.py:14-24` — drop the Phase 1 `from jev_patterns import DEFAULT_MODEL, JEV`; add `from jev_patterns import call, input_tokens, model_name`.
  - Delete: `compact_advisor.py:10` (`import subprocess`, no other use), `:143-172` (`ask_jev`).
  - Modify: `compact_advisor.py:181` — `"model": model_name()`.
  - Modify: `compact_advisor.py:212-217` — `response = call(state, COMPACT_QUESTIONS, job="compact_advisor")`; `answers = response["answers"]`; `row["elapsed"] = response["elapsed"]`; `input_tokens=input_tokens(response)`.
  - Test: `tests/test_compact.py` (unchanged; `:11` already inserts the repo root).
- Interfaces:
  - Consumes (from `jev_patterns`): `call`, `input_tokens(response: dict) -> int`, `model_name(model=None) -> str`.
  - Produces: no new symbols.
  - Unchanged: `ADVISOR_VERSION` `advisor-v1`; row keys (`:177-187`, `:193-227`); `decide_tier`, `tier_message`, `lines_from_env`; the error formatting at `:228-231` (a `JevError` is a `RuntimeError`, so `row["error"]` is `str(e)` with no type prefix, as `no transcript` is today); `import time` stays for `ts` (`:183`); argv `hook claude|codex [--user]`.
- Gotchas: `tests/test_compact.py:361-367` asserts a stub `exit 1` yields a truthy `error` and `printed` false — satisfied by the safe message. The Stop hook is synchronous with a 45 s host timeout (`.claude/settings.json:45`); the library's 40 s default keeps the margin.
- Complexity: mechanical
- Non-goals: tier lines, questions, agy wiring, the `--user` path.
- Depends on: Phase 1
- Acceptance criteria:
  - AC-3.1: Given the Phase 3 file, when `python3 tests/test_compact.py` runs, then it exits 0 with the last line `ok check_scan_keys` and `git diff --stat main -- tests/test_compact.py` empty.
  - AC-3.2: Given the `tests/test_compact.py` stub with `{"exit": 1}` and a three-prompt Claude transcript at 120k tokens, when `compact_advisor.py hook claude` runs, then stdout is empty, exit is 0, and the newest `compact.jsonl` row has `error` equal to `jev exited 1; inspect provider access and limits locally`, `printed` false, `tier` `silent`.
  - AC-3.3: Given `compact_advisor.py` after this phase, when `grep -nE 'subprocess|str\(JEV\)|def ask_jev' compact_advisor.py` runs, then it returns nothing, and `python3 -c "import ast,sys; t=ast.parse(open('compact_advisor.py').read()); print(sorted({n.id for n in ast.walk(t) if isinstance(n, ast.Name)} & {'call','input_tokens','model_name'}))"` prints `['call', 'input_tokens', 'model_name']`.
  - AC-3.4: [live] Given `JEV_COMPACT_LINES=1000,2000,3000` exported and the steps printed by `bash smoke.sh claude compact` followed in an interactive Claude session in the Phase 3 worktree, when `bash smoke.sh claude compact --read` runs afterwards, then it prints a row with `host=claude`, `tier` other than `silent`, `printed=True`, `jev_model` matching `^typesafe/jev-`, and no `error=`; pasted into the PR body with "message seen: yes/no".

### Phase 4 — `skill_router.py`, `fixture_curator.py`, `handoff_check.py`, README
- Outcome: no module but `jev_patterns.py` runs `jev`; the router, curator, and handoff tests pass with one loader line each; the README maps levels 1 to 5 to the code that embodies them.
- Changes:
  - Modify: `skill_router.py:26-27` — delete `JEV`, `DEFAULT_MODEL`; add `from jev_patterns import call, input_tokens, model_name`.
  - Modify: `skill_router.py:279-302` — `def jev(questions: dict, request: str) -> tuple[dict, float]:` body becomes `response = call({"request": request, "recent_context": ""}, questions, job="routing")` and `return response, response["elapsed"]`.
  - Delete: `skill_router.py:305-306` (`usage_tokens`); `:335,373` use `input_tokens(first)` / `input_tokens(second)`.
  - Modify: `skill_router.py:328` — `first.get("model") or model_name()`.
  - Modify: `fixture_curator.py:18-19` — delete; add `from jev_patterns import call, input_tokens`. Delete `import os`, `import subprocess`, `import time` (`:12,14,16`; no other use after the change).
  - Modify: `fixture_curator.py:67-100` — `response = call(f"PROMPT TEXT:\n{record.get('text', '')}", build_curator_questions(), job="curator")`; `answers = response["answers"]`; return `self_contained`, `multiple_defensible` via `score()`, `elapsed: response["elapsed"]`, `input_tokens: input_tokens(response)`.
  - Modify: `handoff_check.py:18-19` — delete `DEFAULT_MODEL`, `DEFAULT_TIMEOUT`; add `from jev_patterns import DEFAULT_TIMEOUT, call, input_tokens, isolated_env as get_isolated_env, model_name`. Delete `import os`, `import subprocess`, `import time` (`:11,14,16`; no other use after the change).
  - Delete: `handoff_check.py:63-66` (`resolve_jev_binary`), `:69-84` (`get_isolated_env`), the `jev_bin` parameter (`:147`), `:156-159` (env build and binary check), `:171-204` (subprocess, JSON, envelope checks), `:209-210` (per-item presence).
  - Modify: `handoff_check.py:142-238` — `response = call(state_content, questions, job="handoff_check", model=model, timeout=timeout)`; keep `:206-229` verdict and confidence checks on `response["answers"]`; `elapsed = response["elapsed"]`; `input_tokens = input_tokens(response)`.
  - Modify: `tests/test_router.py:11-12` — insert `sys.path.insert(0, str(SOURCE.parent))` (add `import sys`) before `spec_from_file_location`.
  - Modify: `tests/test_fixture_curator.py:13-17` — insert `sys.path.insert(0, str(SOURCE.parent))` in `load_module` before `exec_module`.
  - Modify: `tests/test_handoff_check.py:15-19` — same line in `load_module`.
  - Modify: `README.md` — new `## Jev from code` section after `## Skills` (`:112-124`): five subsections `Level 1` to `Level 5`, each one sentence naming the upstream option it mirrors (`README.md:124-200` of the clone) and the JevDev function with its threshold: level 1 → `compact_advisor.decide_tier` `> 0.6`; level 2 → `scope_sentinel.BASH_QUESTIONS` + `gate_bash`; level 3 → `skill_router.suggest` gate average over `GATES` with `GATE_THRESHOLD`; level 4 → `gate_bash` with `BASH_THRESHOLDS`; level 5 → `skill_router.suggest` two-request routing with `FITS_THRESHOLD`; closing line: new callers import `jev_patterns.call` and keep thresholds in code.
  - Test: `tests/test_router.py`, `tests/test_fixture_curator.py`, `tests/test_handoff_check.py`.
- Interfaces:
  - Consumes (from `jev_patterns`): `call`, `input_tokens`, `model_name`, `DEFAULT_TIMEOUT: float`, `isolated_env() -> dict[str, str]`.
  - Produces: `skill_router.jev(questions, request) -> tuple[dict, float]` (unchanged signature, new body); `handoff_check.evaluate_handoff(items, handoff, model=None, timeout=DEFAULT_TIMEOUT) -> HandoffReport` (one parameter fewer); `handoff_check.get_isolated_env` as a re-export of `jev_patterns.isolated_env`.
  - Unchanged: `ROUTER_VERSION`; `suggest()` keys; `GATES`, `GATE_THRESHOLD`, `FITS_THRESHOLD`; the `main` handler at `skill_router.py:885-887` (keeps `subprocess.TimeoutExpired` for the claude/codex arms); `fixture_curator.score` strictness and output lines; `handoff_check` flags, exit codes, verdict enum, the `inspect provider access and limits locally` error line.
- Gotchas: `tests/test_router.py:59-61` sets `JEV_BASE_URL` and `TYPESAFE_API_KEY` in `os.environ` *after* importing the router, and the real `jev` must see both — GC4 forwards them because `isolated_env` reads `os.environ` at call time. `tests/test_handoff_check.py:87-111` calls `module.get_isolated_env()` and expects `RuntimeError` on a missing key: `JevError` subclasses it. The curator's `NAN` stub (`tests/test_fixture_curator.py:71-72`) returns valid JSON with `NaN`, which `json.loads` accepts; presence validation passes and `score()` rejects it (`:107-110`). Deleting `handoff_check.py:158-159` changes the missing-binary error from `FileNotFoundError("Jev binary not found …")` to `JevError("FileNotFoundError: [Errno 2] …")`; `main` catches both through `except Exception` (`:307-309`) and prints `Error: …` with exit 1, so the CLI contract holds.
- Complexity: mechanical
- Non-goals: issue #28 (agy router); changing router thresholds or sharding; new helpers (DR-2).
- Depends on: Phases 1, 2, and 3. The module edits need only Phase 1, but AC-4.3's repo-wide greps hold only once `ask_jev_files.py` (`NO_KEY` at `:60`, `"-j"` at `:163`) and `compact_advisor.py` (`"-j"` at `:157`) have migrated, so this phase lands last (§9).
- Acceptance criteria:
  - AC-4.1: Given the Phase 4 files, when `python3 tests/test_router.py`, `python3 tests/test_fixture_curator.py`, and `python3 tests/test_handoff_check.py` run, then each exits 0 (last lines `PASS: HTTP contract…`, `All tests passed.`, `All tests passed.`) and `git diff --numstat main -- tests/test_router.py tests/test_fixture_curator.py tests/test_handoff_check.py` shows at most 2 insertions and 0 deletions per file (one `sys.path` line, plus `import sys` where absent).
  - AC-4.2: Given `tests/test_handoff_check.py`'s `STUB_JEV_CRASH` (stderr `Fatal authentication error: Bearer secret_leaked_key`, exit 2), when `handoff_check.py --ledger L --handoff H` runs, then exit is 1, stderr contains `inspect provider access and limits locally`, and `secret_leaked_key` appears in neither stdout nor stderr; given a stub that exits 0 with `{"answers": {}}`, stderr contains `jev response missing answer 'item_0'` and exit is 1.
  - AC-4.3: Given the full tree after this phase, when `grep -n '"-j"' *.py` and `grep -n 'str(JEV)' *.py` run, then each prints exactly one line, in `jev_patterns.py`; `grep -nE '^(JEV|DEFAULT_MODEL|NO_KEY) = ' *.py` prints exactly three lines, all in `jev_patterns.py` (GC6); and `grep -nE 'def usage_tokens|def resolve_jev_binary|def get_isolated_env|jev_bin' skill_router.py handoff_check.py fixture_curator.py` returns nothing.
  - AC-4.4: Given `README.md`, when `grep -nE '^## Jev from code|^### Level [1-5]' README.md` runs, then it prints six lines in that order, and the section names `jev_patterns.call`, `decide_tier`, `gate_bash`, `BASH_THRESHOLDS`, `GATE_THRESHOLD`, and `FITS_THRESHOLD`; all ten pre-existing tests plus `tests/test_jev_patterns.py` pass (`for t in tests/test_*.py; do python3 "$t" || echo "FAIL $t"; done` prints no `FAIL`); and `git ls-files | grep -E '^(\.local|transcripts)/'` prints nothing (GC10).
  - AC-4.5: [live] Given the real key, when `bash with_jev_key.sh python3 skill_router.py --host claude route 'Help me create a reusable skill.'` runs in the Phase 4 worktree, then it prints JSON with `model` matching `^typesafe/jev-`, `requests` 1 or 2, and `input_tokens` > 0; and `bash smoke.sh claude bash` prints a row with `jev_model` matching `^typesafe/jev-` and no `error=`; both pasted into the PR body.

## 8. Test Strategy

All tests are stdlib, run as `python3 tests/test_<name>.py`, and replace Jev with a stub executable on `JEV_BIN` (`tests/test_sentinel.py:12-57`). `tests/test_jev_patterns.py` imports the library in-process after setting `JEV_BIN` (DR-7) and drives every `call` branch with a recording stub whose behaviour comes from a `cfg.json` (exit code, stderr lines, sleep seconds, stdout override). `tests/test_router.py` keeps exercising the real `jev` script over HTTP (`:17-53`), which is the one test of GC4's `JEV_BASE_URL` forwarding.

**Regression test per defect** (fails on today's code, passes after):

| Defect | Test | Fails today because |
|---|---|---|
| D1 | `tests/test_jev_patterns.py::check_call_shape` (AC-1.1) and the GC2 grep (AC-4.3) | `jev_patterns` does not exist; six `"-j"` hits |
| D2 | `tests/test_jev_patterns.py::check_missing_answers` (AC-1.2) at the library; AC-2.2 at the CLI, a shell check with the `tests/test_ask_jev_files.py` stub recorded in the Phase 2 PR body (GC8 forbids a new assertion in that file) | `files` raises `KeyError` at `ask_jev_files.py:256` |
| D3 | `tests/test_jev_patterns.py::check_isolated_env` (AC-1.1: `GH_TOKEN` absent from the stub's environment); the sentinel reaches Jev only through `call` once AC-1.4's grep holds | the sentinel passes the whole environment |
| D4 | `tests/test_jev_patterns.py::check_input_tokens_null` (AC-1.2) | `scope_sentinel.py:268` raises `AttributeError` on `usage: null` |
| D5 | AC-4.4 grep | the README section does not exist |

**Contract tests** (§2 must-not-break): every pre-existing test file is the contract test for its module and is run unchanged in assertions (GC8): `tests/test_sentinel.py` (rows, 2 s bound, error rows, judge cap, env of `with_jev_key.sh`), `tests/test_ask_jev_files.py` (exit codes, `jev: HTTP 429…`, redaction of file content), `tests/test_compact.py` (tiers, error rows), `tests/test_router.py` (two-request contract, `input_tokens` sum), `tests/test_fixture_curator.py` (NaN and missing-answer failures), `tests/test_handoff_check.py` (sanitised crash, `get_isolated_env`).

**Boundary and replay tests**: `timeout=0.5` against a 3 s stub (AC-1.2); a stderr of 300 characters → `.stderr` length 200; an empty stderr with exit 2 → `.stderr` `""` and the safe message; `JEV_MODEL` set and `model="x"` passed → argv `-m x`; a `str` state that starts with `{` is passed verbatim (the `jev` script decides JSON-ness, `jev:68`).

**Derived criteria** (each AC list run against empty input, maximum size, invalid types, concurrency, dependency failure, permission denied): an empty `questions` dict → `call` still runs and validates nothing (no caller does this; documented, not guarded); a `state` that `json.dumps` cannot encode → `TypeError` propagates (today's behaviour at `scope_sentinel.py:242`); 16 concurrent `call`s from the `files` pool must each get their own `elapsed` (AC-2.1 fixture has 23 files); a non-executable `JEV_BIN` → `JevError("PermissionError: …")` (covered under AC-1.2's `OSError` branch by a stub with mode 0644); `TMPDIR` unset in the parent → absent in the child (allow-list copies only what exists).

**Traceability matrix**

| D / GC | Criterion | Check | Test |
|---|---|---|---|
| D1, D3, GC3, GC4 | AC-1.1 | stub sees argv `-m m1 -q <json> -j t`, stdin JSON or verbatim `str`, env ⊆ allow-list with `GH_TOKEN` absent; return has `answers`, float `elapsed`; `input_tokens` matches | `tests/test_jev_patterns.py` |
| D1, D2, D4, GC5 | AC-1.2 | exit 2 + secret stderr → `JevError` safe `str`, `returncode` 2, `.stderr` first line; no key → `NO_KEY`, stub never run; 3 s stub at 0.5 s → `jev timed out after 0.5s`; `not json` → non-JSON error; `{"answers": {}}` → `missing answer 'q'`; `usage: null` → 0 | `tests/test_jev_patterns.py` |
| GC8 | AC-1.3 | `tests/test_sentinel.py` passes with exactly one inserted line | `tests/test_sentinel.py`, `git diff --stat` |
| D1, GC1, GC2, GC7, GC9 | AC-1.4 | stub exit 1 → row `gate` bash, `error` has the safe message, no `effect`; hook exit 0, empty stdout, < 2 s; no `subprocess.run` left in the sentinel; `jev_patterns.py` imports only stdlib modules | `tests/test_sentinel.py`, grep |
| D1 | AC-1.5 | `smoke.sh claude bash` → `host=claude`, `host_model` set, `jev_model` `^typesafe/jev-`, no error | live, PR body |
| GC8 | AC-2.1 | `tests/test_ask_jev_files.py` passes unchanged | `tests/test_ask_jev_files.py` |
| D2 | AC-2.2 | zero-exit `{"model": …}` → `files` exit 0, `skipped` reason `jev: jev response missing 'answers' object`, no traceback | shell with the test stub |
| D1, GC5 | AC-2.3 | exit 2 with `Authorization: Bearer sk-…` → `{"error": "jev: HTTP 401 Authorization: Bearer [REDACTED] rejected"}`, exit 2 | shell with the test stub |
| D1, GC2 | AC-2.4 | only the `--command` `subprocess.run` remains; `jev_call`, `has_key`, `model_of`, `NO_KEY` gone | grep |
| D1 | AC-2.5 | `smoke.sh claude ask` → reply with `kind`, `flaky`; row `jev_model` `^typesafe/jev-` | live, PR body |
| GC8 | AC-3.1 | `tests/test_compact.py` passes unchanged | `tests/test_compact.py` |
| D1, GC7 | AC-3.2 | stub exit 1 → row `error` `jev exited 1; …`, `printed` false, `tier` silent, empty stdout | `tests/test_compact.py` fixture |
| D1, GC2 | AC-3.3 | no `subprocess`, `str(JEV)`, `ask_jev` in the advisor; `call`, `input_tokens`, `model_name` referenced | grep, `ast` one-liner |
| D1 | AC-3.4 | interactive compact smoke → `tier` ≠ silent, `printed=True`, `jev_model` `^typesafe/jev-` | live, PR body |
| GC8 | AC-4.1 | router, curator, handoff tests pass with ≤ 2 inserted lines each | three tests, `git diff --numstat` |
| D1, D2, GC5 | AC-4.2 | crash stub → exit 1, safe line, no secret; `{"answers": {}}` → `missing answer 'item_0'`, exit 1 | `tests/test_handoff_check.py` stubs |
| D1, GC2, GC6 | AC-4.3 | exactly one `"-j"` and one `str(JEV)` in the repo, both in `jev_patterns.py`; `JEV`, `DEFAULT_MODEL`, `NO_KEY` defined only there; dead helpers gone | grep |
| D5, GC8, GC10 | AC-4.4 | README `## Jev from code` with `### Level 1`…`5` naming the six symbols; full suite green; nothing under `.local/` or `transcripts/` tracked | grep, shell loop |
| D1 | AC-4.5 | live `route` JSON with `model` `^typesafe/jev-`; `smoke.sh claude bash` row clean | live, PR body |

## 9. Rollout & Verification

**Sequence.** Four phases, four PRs after this spec PR, each from its own worktree off `main`:

1. `feat/jev-patterns-p1-library-sentinel` — adds `jev_patterns.py`, its test, migrates the sentinel, moves two import lines. Claude, Codex, and agy project hooks pick up the new transport at the next tool call with no config change and no Codex re-trust (§4). After merge: `git -C ~/JevDev pull --ff-only` so user-scope hooks import the module. **Shipped: #39.**
2. `feat/jev-patterns-p2-ask-jev-files` — CLI only; the ask-jev skill's recipes keep working (`tests/test_ask_jev_skill.py` runs the fenced blocks with the stub). **Shipped: #43** (review follow-ups: #44).
3. `feat/jev-patterns-p3-compact-advisor` — Stop hook; no config change.
4. `feat/jev-patterns-p4-router-curator-handoff` — the three CLIs plus the router hook, three loader lines, README section. Independent of 2 and 3; lands last so the GC2 grep is the merge check.

Each PR body carries: the test command(s) and their last line, the phase's live line(s) (`smoke.sh` output, or the `route` JSON's `model`/`requests`/`input_tokens`), `Refs #17`, and for Phase 4 `Refs #28`. Merge from the primary checkout, then `git worktree remove`, `git branch -d`, `git push origin --delete` per `AGENTS.md`.

**Backward compatibility.** Row keys are unchanged; the only value-level change is the sentinel's `error` prefix for transport failures (`RuntimeError:` → `JevError:`), which #17 analysis should match on the message text (`jev exited`, `jev timed out`) rather than the prefix. `handoff_check.get_isolated_env` remains importable. No shim is added and nothing is removed later; the deletions are in the phases that replace them.

**Rollback.** Trigger: a hook row rate with `error` above 2 % after a phase, a `files`/`ask` run that cannot reach Jev while `jev -n` succeeds, or a Stop hook delaying the prompt past 45 s. Procedure: revert the phase PR on `main` and `git -C ~/JevDev pull --ff-only`; project hooks and user-scope hooks follow the checkout. Phase 1's revert also reverts the two import moves, so Phases 2 and 3 cannot be live without it (they depend on it by import).

**Post-cutover gates** (measured on `~/.local/state/jevdev/*.jsonl` and this repo's `.local/` seven days after Phase 4):

| Gate | Measure | Pass value | On fail |
|---|---|---|---|
| Transport parity | share of sentinel and compact rows with `error` starting `JevError:` or equal to the safe messages | < 2 % | compare with the pre-migration share; if higher, inspect `JEV_BASE_URL`/proxy assumptions (§10) |
| Isolation holds | `env` recorded by a stub run through the Claude hook (`tests/test_sentinel.py` harness with `GH_TOKEN` set) | `GH_TOKEN` absent | AC-1.1 regression |
| Single transport | `grep -n '"-j"' *.py` on `main` | one line | a new caller copied the pattern; open an issue, migrate it |

## 10. Risks & Open Questions

| Risk | Likelihood / Impact | Mitigation or contingency |
|---|---|---|
| A proxy or CA variable (`HTTPS_PROXY`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`) is needed on another machine and GC4 drops it, so every `curl` inside `jev` fails (DR-4) — the largest risk, because it turns every hook row into an error row at once | Low here (none set, §4) / High elsewhere | the error rows are visible within one tool call; extend `SAFE_ENV` by PR with the variable named; `jev -n` still prints the route for diagnosis |
| `start_new_session=True` leaves a `jev`/`curl` child running up to 30 s after a Ctrl-C in a CLI, or after a host kills a hook's process group at its timeout (Stop hook 45 s, `.claude/settings.json:45`) (DR-4) | Medium / Negligible | bounded by `curl -m 30` (`jev:101`); no state is written by the child; the sentinel judge already outlives the hook by design (`scope_sentinel.py:487`) |
| The brief asked for levels 1 to 5 "as helpers"; DR-2 ships the client plus a README map instead, and a reviewer who wanted `gate`/`score`/`route` functions gets none (DR-2) | Medium / Medium | the PR body states the cut as the headline judgment call; adding a helper later is additive and lands with its first caller, so nothing built here blocks it |
| Sentinel `error` rows change prefix (`JevError:`), skewing a #17 script that groups on the prefix (DR-3) | Medium / Low | §9 compatibility note; rows carry `sentinel_version` unchanged so the cut-over date is recoverable from `ts` |
| `ask_jev_files` emits a provider error line to the agent that `redact()` does not match (DR-3) | Low / Low | `SECRETS` covers `Authorization`, `Bearer`, `token=`, `sk-`, `ghp_` shapes (`scope_sentinel.py:41-53`); the line is the first one only and ≤ 200 chars |
| A test imports `jev_patterns` before setting `JEV_BIN`, binding the real binary (DR-7) | Low / Low | `tests/test_jev_patterns.py` sets it first, as `tests/test_ask_jev_files.py:112` does; a wrong binding fails loudly with a real network error |
| The user-scope checkout `/home/alex/JevDev` is not pulled after Phase 1, so its `scope_sentinel.py` imports a missing module | Medium / Medium | existing merge checklist step (`README.md:145`); a failing import produces no row at all, so the §9 parity gate catches it |
| Two transports coexist between Phases 1 and 4 (DR-8) | Certain / Low | each phase's AC pins its own module; GC2's grep is the Phase 4 gate |
| Presence-only validation lets a wrong-typed answer through to a `KeyError` in the caller (DR-5) | Low / Low | unchanged behaviour; rows and `pick failed:` errors keep it visible |
| `elapsed` injected into the response collides with a future provider field of the same name (DR-6) | Low / Low | the key is overwritten by the library after parsing; rename if the provider ever ships one |
| Live smokes need a key and a host; a phase merged on tests alone lacks its live line | Medium / Low | GC11 makes the live line part of the PR body; the reviewer blocks without it |

**Open questions:** none. The migration question was settled at the Phase 2 gate (DR-1); the API cut (DR-2) is recorded as the headline judgment call for the PR reviewer to overturn before Phase 1 starts.
