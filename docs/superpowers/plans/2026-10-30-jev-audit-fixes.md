# Jev Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every finding in the 2026-10-30 VistaMobileBE Jev usage audit so the user-scope hooks explain their own failures, stop flagging legitimate writes, and so a machine rebuilt from `main` gets the full tool.

**Architecture:** All hooks already run from the user-scope install (`~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.gemini/config/hooks.json` point at `/home/alex/JevDev/*.py`), so every fix lands in JevDev `main` and goes live for every repo on `git -C ~/JevDev pull`. `install_user.py` gains two `~/.local/bin` links so `jev` and `jev-selfcheck` are owned by the repo too. Tests stay offline, plain `assert` scripts under `tests/`, driven by the existing stub-`jev` helpers.

**Tech Stack:** Python 3 stdlib, bash, `curl`, JSONL logs under `~/.local/state/jevdev`.

**Spec:** `docs/audit/2026-10-30-vistamobile-jev-usage-audit.md` (copy of the audit; findings are in "Findings, most urgent first").

## Global Constraints

- Hooks fail open: an exception sets `row["error"]` and the row is still appended; never block on an error.
- Logs never carry raw commands, instructions or file content unredacted: everything written goes through `scope_sentinel.redact`/`clip`.
- `JevError.stderr` is at most the first non-empty stderr line, 200 chars (`jev_patterns.py:97-101`); do not log more.
- No paid Jev calls in tests; every test uses a stub `jev` on `PATH`.
- Run `python3 tests/test_router.py` after any router change (AGENTS.md); run the touched test file after each task.
- All changes on this branch (`claude/vista-mobile-audit-fix-f1d9ba`), one PR.

## Review Focus

1. A `jev` stderr line containing a key fragment (`ts_...`, `sk-or-...`) must reach the log redacted, never raw. Test in Task 1.
2. A write to `/tmp/claude-1000/<other-session>/scratchpad/x` from a different session must still count as outside the repo. Test in Task 3.
3. A `jev` response with no `usage` object must log `estimated_usd: 0.0`, not crash. Test in Task 5.
4. `jev-selfcheck` run with stdin at `/dev/null` (CI, hook) must not hang in the fake curl. Test in Task 4.
5. A Codex `apply_patch` event with no `*** Add/Update File:` header must still log `tool: "apply_patch"` and no error. Test in Task 2.

---

### Task 0: Merge the wrapper PR (manual, user)

**Files:** none in this branch.

- [ ] **Step 1:** Review and merge [JevDev#52](https://github.com/z0rd0n88/JevDev/pull/52) (`bin/jev`, byte-identical to live `~/.local/bin/jev`) from the primary checkout, then `git -C ~/JevDev pull --ff-only`.
- [ ] **Step 2:** Rebase this branch on `main`: `git rebase main` in this worktree. Expected: clean; #52 touches `README.md`, `bin/jev`, `tests/test_jev_cli.py`, `tests/test_router.py`, none of which Tasks 1-3 edit before this point.

Task 4 depends on `bin/jev` existing.

### Task 1: Hook logs keep the redacted `jev` stderr line (High)

**Files:**
- Modify: `scope_sentinel.py:510-512` (bash/write hook `except`), `compact_advisor.py:194-197`
- Test: `tests/test_sentinel.py`, `tests/test_compact.py`

**Interfaces:**
- Produces: `error_detail(e: BaseException) -> str` in `scope_sentinel.py`, returns `f"{type(e).__name__}: {e}"` for a plain exception, and for a `RuntimeError` just `str(e)` (the advisor's existing rule), with `" | " + clip(redact(e.stderr))` appended when `getattr(e, "stderr", "")` is non-empty. `compact_advisor.py` imports it from `scope_sentinel` (it already imports from there).

- [ ] **Step 1: Write the failing tests.** In `tests/test_sentinel.py` add a stub `jev` variant that prints `curl: (22) HTTP 429 key ts_secret123` to stderr and exits 2; run the bash hook with it. Assert:

```python
assert "jev exited 2" in row["error"] and "HTTP 429" in row["error"], row
assert "ts_secret123" not in row["error"], row   # Review Focus 1
```

Same shape in `tests/test_compact.py` for the advisor.

- [ ] **Step 2:** Run `python3 tests/test_sentinel.py && python3 tests/test_compact.py`. Expected: FAIL, `error` is only `JevError: jev exited 2; inspect provider access and limits locally`.
- [ ] **Step 3:** Implement `error_detail` and use it in both `except` blocks.
- [ ] **Step 4:** Run both test files. Expected: PASS.
- [ ] **Step 5:** Commit: `git add scope_sentinel.py compact_advisor.py tests/test_sentinel.py tests/test_compact.py && git commit -m "fix(hooks): log the redacted jev stderr line on failure"`.

### Task 2: Log the tool name; correct the Codex write-gate cell (Medium)

**Files:**
- Modify: `scope_sentinel.py:418-455` (`tool_target`), `:490-492` (`row.update`)
- Modify: `check_install.py:160-166` (codex write cell), `README.md:64`, `README.md:165`
- Test: `tests/test_sentinel.py`, `tests/test_check_install.py`

**Interfaces:**
- Produces: `tool_target` returns an extra key `"tool": name` (the host's tool name string: `Bash`, `Write`, `apply_patch`, `run_command`...). `run_hook` copies it to `row["tool"]`.

- [ ] **Step 1: Failing tests.** In `tests/test_sentinel.py` assert `row["tool"] == "Write"` on an existing Claude write case and `row["tool"] == "apply_patch"` on an existing Codex patch case; add one Codex `apply_patch` event whose `command` has no file header and assert the row has `tool == "apply_patch"` and no `error` (Review Focus 5; today `tool_target` returns `None` and the hook raises on `target["cwd"]`, so decide: log `gate: "write"`, `path: None`, `skipped: "no patch header"`). In `tests/test_check_install.py` assert the Codex write cell is `"ok"` when the matcher is trusted.
- [ ] **Step 2:** Run `python3 tests/test_sentinel.py; python3 tests/test_check_install.py`. Expected: FAIL on `KeyError: 'tool'` and on the cell text.
- [ ] **Step 3:** Implement: add `"tool"` to every `tool_target` return dict; in `check_install.py` drop `ok="ok (unavailable here)"` from the Codex write cell; rewrite README line 64 to say the Codex write gate fires on native `apply_patch` (395 rows Oct 16-30 in VistaMobileBE) and delete the `ok (unavailable here)` legend row at line 165.
- [ ] **Step 4:** Run both test files. Expected: PASS.
- [ ] **Step 5:** Commit: `git add scope_sentinel.py check_install.py README.md tests/test_sentinel.py tests/test_check_install.py && git commit -m "fix(install): codex write gate fires; log tool name per row"`.

### Task 3: Write gate allows the session scratchpad (High)

**Files:**
- Modify: `scope_sentinel.py:516-523` (`judge_write_event`), module constants near `RISKY` (`:29`)
- Test: `tests/test_sentinel.py`

**Interfaces:**
- Produces: `SCRATCHPAD = re.compile(r"^/tmp/claude-\d+/[^/]+/([0-9a-f-]{36})/")` and `is_scratchpad(path: str, session_id) -> bool` (match and group(1) == session_id). When true, `judge_write_event` sets `row.update(path=target["path"], scope="scratchpad")` and returns without a Jev call or a `would_block`.

Assumption (state in PR): Claude hook events carry no list of `--add-dir` directories, so writes into *other* repos stay `would_block: outside the repo` until the labeling in Task 7 says otherwise. The alternative, allowing any git repo under `$HOME`, would disable the rule.

- [ ] **Step 1: Failing tests.** Claude Write event, `session_id` `S`, path `/tmp/claude-1000/-home-alex-VistaMobileBE/S/scratchpad/notes.md`: assert `row.get("would_block") is None` and `row["scope"] == "scratchpad"`. Same path with session `T` in the event: assert `row["would_block"] is True` (Review Focus 2). Path `/home/alex/BotHaus/x.py` from a VistaMobileBE cwd: still `would_block` with `block_reason` starting `outside the repo`.
- [ ] **Step 2:** Run `python3 tests/test_sentinel.py`. Expected: FAIL, first case has `would_block: True`.
- [ ] **Step 3:** Implement `is_scratchpad` and the early return.
- [ ] **Step 4:** Run `python3 tests/test_sentinel.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `git add scope_sentinel.py tests/test_sentinel.py && git commit -m "fix(write-gate): session scratchpad is not outside the repo"`.

### Task 4: `jev-selfcheck` moves into the repo, gets a stdin-aware fake curl, and both binaries install from `install_user.py` (Medium + user-scope install)

**Files:**
- Create: `bin/jev-selfcheck` (copy of `~/.local/bin/jev-selfcheck`, then edit lines 76-83)
- Modify: `install_user.py:104-125` (`link_plan`), `README.md` "User-scope install" (`:170-181`)
- Test: `tests/test_install_user.py`, `tests/test_jev_cli.py` (from #52)

**Interfaces:**
- Produces: `install_user.py` links `~/.local/bin/jev -> <jevdev>/bin/jev` and `~/.local/bin/jev-selfcheck -> <jevdev>/bin/jev-selfcheck` with the same create/keep/relink/refuse rules as the skill links (`BIN = ("jev", "jev-selfcheck")`, link dir `.local/bin`). A real file at either path is refused with exit 2, like the skills. `--remove` removes links we own.

- [ ] **Step 1: Failing install test.** In `tests/test_install_user.py`: with a temp `--home`, after `install_user.py` run, `home/.local/bin/jev` and `.../jev-selfcheck` are symlinks whose `readlink()` starts with the jevdev path; a pre-existing regular file at `home/.local/bin/jev` makes the run exit 2 and touch nothing.
- [ ] **Step 2:** Run `python3 tests/test_install_user.py`. Expected: FAIL, links absent.
- [ ] **Step 3:** Extend `link_plan` to iterate `BIN` into `.local/bin`; add the two paths to the printed plan and `--remove`.
- [ ] **Step 4:** Run `python3 tests/test_install_user.py`. Expected: PASS.
- [ ] **Step 5: Fix the fake curl** in `bin/jev-selfcheck`. The fake curl writes `"$@"` to `$fake/args` and stdin to `$fake/stdin` with `{ [ -t 0 ] || cat; } >"$fake/stdin"` (Review Focus 4: `/dev/null` stdin returns at once). Before each of the two runs `rm -f "$fake/args" "$fake/stdin"`. Checks become:

```bash
grep -qs ts_secret "$fake/args" "$fake/stdin" && { echo "FAIL local route was sent the key"; fail=1; } || echo "ok   local route sends no key"
grep -qs 'Bearer ts_secret' "$fake/stdin" && echo "ok   own route sends the key" || { echo "FAIL own route lost the key"; fail=1; }
```

- [ ] **Step 6:** Verify: `PATH=$PWD/bin:$PATH bash bin/jev-selfcheck`. Expected: every line `ok`, exit 0. Then `bash bin/jev-selfcheck </dev/null`: same, no hang.
- [ ] **Step 7:** README "User-scope install": add that step 1 now also links `jev` and `jev-selfcheck` into `~/.local/bin`, and add `jev-selfcheck` to the checks in step 5.
- [ ] **Step 8:** Commit: `git add bin/jev-selfcheck install_user.py README.md tests/test_install_user.py && git commit -m "feat(install): link jev and a fixed jev-selfcheck into ~/.local/bin"`.

### Task 5: Hook rows carry `estimated_usd` (Low)

**Files:**
- Modify: `jev_patterns.py:63-64`, `skill_router.py` (import the constant instead of defining it; lines `:314`, `:350` unchanged), `scope_sentinel.py` where `input_tokens=` is set in `judge_bash`/`judge_write_event`, `compact_advisor.py:183`
- Test: `tests/test_jev_patterns.py`, `tests/test_sentinel.py`, `tests/test_router.py`

**Interfaces:**
- Produces: `PRICE_PER_MILLION_INPUT` moves from `skill_router.py` to `jev_patterns.py` (same value); `estimated_usd(response: dict) -> float = input_tokens(response) * PRICE_PER_MILLION_INPUT / 1_000_000`.

- [ ] **Step 1: Failing tests.** `tests/test_jev_patterns.py`: `estimated_usd({"usage": {"input_tokens": 1_000_000}}) == PRICE_PER_MILLION_INPUT` and `estimated_usd({}) == 0.0` (Review Focus 3). `tests/test_sentinel.py`: an answered bash row has `row["estimated_usd"] == row["input_tokens"] * PRICE_PER_MILLION_INPUT / 1_000_000`.
- [ ] **Step 2:** Run the three test files. Expected: FAIL on import.
- [ ] **Step 3:** Implement; set `row["estimated_usd"]` next to every `input_tokens=` in the two hooks.
- [ ] **Step 4:** Run `python3 tests/test_jev_patterns.py; python3 tests/test_sentinel.py; python3 tests/test_compact.py; python3 tests/test_router.py`. Expected: all PASS.
- [ ] **Step 5:** Commit: `git add jev_patterns.py skill_router.py scope_sentinel.py compact_advisor.py tests/ && git commit -m "feat(hooks): log estimated_usd per row"`.

### Task 6: Reproduce "no user instruction found in transcript" on Codex and agy (High, investigation)

**Files:**
- Create: `tests/fixtures/codex_rollout_no_prompt.jsonl`, `tests/fixtures/agy_transcript_no_prompt.jsonl` (authored from real transcripts, with the typed text replaced by `placeholder` and everything else minimal; review before commit per AGENTS.md)
- Modify: `scope_sentinel.py:385-400` (`codex_user_text`) and `agy_user_text` as the fixtures dictate
- Test: `tests/test_sentinel.py`

- [ ] **Step 1:** From `~/.local/state/jevdev/sentinel.jsonl`, take the newest Codex and agy rows with that error; open the `transcript_path` each one names (Codex rollouts under `~/.codex/sessions/`, agy under `~/.gemini/`). Run `python3 -c 'from scope_sentinel import latest_user_prompt; print(repr(latest_user_prompt(P, HOST)))'` on each. Expected: `''`.
- [ ] **Step 2:** Find the entry that holds the typed text and record its `type`/`payload.type`/`item.type` shape. Cut the transcript to the shortest prefix that still reproduces `''`, replace the user text with `placeholder`, save as the two fixtures.
- [ ] **Step 3: Failing test.** `latest_user_prompt(fixture, "codex") == "placeholder"` and the same for agy.
- [ ] **Step 4:** Extend `codex_user_text` / `agy_user_text` to the shape found. Run `python3 tests/test_sentinel.py`. Expected: PASS.
- [ ] **Step 5:** Add the stated rule to README "Shadow hooks": a row with no instruction is never a block; it is logged with `error` and counted separately when a threshold is chosen.
- [ ] **Step 6:** Commit: `git add scope_sentinel.py tests/fixtures/ tests/test_sentinel.py README.md && git commit -m "fix(sentinel): read user text from newer Codex/agy transcript shapes"`.

If Step 1 does *not* reproduce (the shape has since changed or the transcript was truncated at hook time), record that in the PR and keep only the README rule.

### Task 7: Finish, go live, and the two decisions (user)

- [ ] **Step 1:** `for t in tests/test_*.py; do python3 "$t" >/dev/null 2>&1 && echo "PASS $t" || echo "FAIL $t"; done`. Expected: 12 PASS (13 once JevDev#52 adds tests/test_jev_cli.py).
- [ ] **Step 2:** Open the PR (`Closes` nothing; link the audit path in the body), merge from `~/JevDev`, `git -C ~/JevDev pull --ff-only`, then `python3 ~/JevDev/install_user.py` and `python3 ~/JevDev/check_install.py --scope user` (exit 0, Codex write cell `ok`) and `jev-selfcheck` (exit 0). Hooks pick the new code up on their next run; no host restart.
- [ ] **Step 3 (labeling, before any blocking threshold):** sample 50 `would_block` write rows and the 83 flagged bash rows from `sentinel.jsonl` for VistaMobileBE, label each right/wrong per the README's labeling rule, and only then pick a threshold. Not code; owner: user.
- [ ] **Step 4 (decision):** ship or park each of `skill_router`, `fixture_curator`, `handoff_check`, `test_escrow`, together with open PRs #48, #15, #12. Anything shipped gets a `check_install.py` row.
- [ ] **Step 5 (other repo):** add one line to `VistaMobileBE/AGENTS.md` pointing at `ask-jev` for judgment calls, so the manual tools get used. Separate PR in VistaMarkets/VistaMobileBE.
