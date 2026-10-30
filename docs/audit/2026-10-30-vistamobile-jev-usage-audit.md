# Jev install and usage audit, seen from VistaMobileBE

Date: 2026-10-30. JevDev checkout: `main` at `36ae4a2`, in sync with origin. All times are local, UTC-7.

## Summary

All six features that `check_install.py` tracks are installed at user scope, and Jev is reachable. The automatic hooks run constantly in VistaMobileBE. The manual tools have run once in 15 days, and the four prototypes have never run from this repo.

The hooks only record verdicts, so nothing has depended on them yet. That is the good news, because the logs show problems that must be fixed before any gate goes live. The most urgent is that hook logs throw away the reason a Jev call failed, which left a 49-minute failure burst today with no explanation.

## Install state

`python3 check_install.py --scope user` exits 0:

| Feature | Claude | Codex | agy |
|---|---|---|---|
| `hyper-jev` skill | ok | ok | ok |
| `ask-jev` skill | ok | ok | ok |
| Bash gate | ok | ok | ok |
| Write gate | ok | ok (unavailable here) | ok |
| Compaction advisor | ok | ok | n/a (unavailable) |
| `ask_jev_files` CLI | ok | ok | ok |

Running it with `--root /home/alex/VistaMobileBE` shows every available cell as `missing` and exits 1. That is expected, because this repo relies on the user-scope install and has no project-level Jev config.

All 12 files in `tests/test_*.py` pass offline. Live access is proven by the logs: the newest answer for this repo came at 14:32 today from `typesafe/jev-1.14-20261014`, routed through OpenRouter. I made no paid test call.

## Usage in VistaMobileBE, Oct 16 to 30

| Feature | Use |
|---|---|
| Bash gate | 17,278 rows: Claude 15,423, Codex 1,832, agy 23 |
| Write gate | 1,856 rows: Claude 1,461, Codex 395 |
| Compaction advisor | 802 runs, 55 printed advice |
| `ask_jev_files` CLI | 1 run, Oct 19 |
| `ask-jev` skill | 1 call, Oct 19 |
| `hyper-jev` skill | 0 calls |
| `skill_router`, `fixture_curator`, `handoff_check`, `test_escrow` | 0 runs, not installed |

Across the gates, Jev answered about 17,500 of about 19,100 rows, with a median time of 0.28 s and a p95 of 0.61 s. They sent about 28.1M input tokens.

The 1,028 rows with errors in this repo break down as follows:

| Error | Rows |
|---|---|
| `no user instruction found in transcript` | 484 |
| `jev exited 2; inspect provider access and limits locally` | 456 |
| `KeyError: 'transcriptPath'`, Codex, last seen Oct 23 | 63 |
| `skipped: 4 judges already running` | 24 |
| `jev timed out after 40s` | 1 |

## Findings, most urgent first

### High: hook logs drop the reason a Jev call failed

From 13:00:29 to 13:49:12 today, 469 Claude rows across all repos failed with the same generic `jev exited 2` message: 440 from the bash gate and 29 from the write gate. The compaction advisor logged 15 errors in the same window. Jev still gave 191 answers during those 49 minutes, so this was partial failure, not a full outage. The first answer after the last failure came at 13:49:22.

I can't tell you the cause, and neither can the logs. `jev_patterns.py:97-99` keeps the first stderr line on `JevError.stderr`, and `ask_jev_files.py:215` and `:422` report it with `redact(e.stderr)`. `scope_sentinel.py` and `compact_advisor.py` never read it.

Fix: write the redacted stderr line into the `error` field of both logs, and cover it with a stub `jev` test. Do this first, since the next burst will otherwise be just as unexplained.

### High: the gate misses verdicts when it can't find the user's instruction

`scope_sentinel.py:502` raises `no user instruction found in transcript`. Across all repos that is 2,323 of 29,417 rows, about 8%: agy 1,708, Codex 586, Claude 29. It is still happening, with agy and Codex both last seen Oct 29. In this repo, Codex hit it 214 times in the last 7 days.

I did not look for the root cause. Fix: reproduce it against a real Codex rollout and a real agy transcript, then add both as fixtures. A live gate needs a stated rule for this case, since these rows carry no verdict at all.

### High: the write gate's `would_block` would refuse normal agent writes

In this repo, 606 of 607 write-gate `would_block` rows have the reason `outside the repo`. At least 245 of them are `/tmp/claude-*` paths, which are the agent's session scratchpad. Others point at different repos under `/home/alex`. Turned on as written, this rule would mostly stop legitimate work.

The bash gate flagged 83 rows, mainly on destructive intent. I didn't label those or sample the write rows beyond their path prefix, so neither set says anything yet about accuracy.

Fix: allow the session scratchpad and directories added to the session, then label rows as the README already requires before choosing a blocking threshold.

### Medium: `main` has no source for the deployed wrapper

`bin/jev` exists only on the open [JevDev#52](https://github.com/z0rd0n88/JevDev/pull/52), head `7d16cbb`, which GitHub reports as mergeable. That file is byte-identical to the live `~/.local/bin/jev`. Everything else in the repo routes through this wrapper, so a machine rebuilt from `main` would have no copy of it.

Fix: review and merge the PR.

### Medium: `jev-selfcheck` reports a false failure and has one check that can't fail

It prints `FAIL own route lost the key`. The wrapper now sends the auth header over stdin with `curl -H @-`, while the fake curl at `~/.local/bin/jev-selfcheck:79` records only its arguments. For the same reason, the `local route sends no key` check at line 83 passes without testing anything.

I ran both routes with a fake key through a fake curl that also captures stdin. The real route sends `Bearer ts_secret` on stdin and the local route sends no key, and neither puts it in the arguments. So the wrapper is correct and the test is wrong.

Fix: capture stdin in the fake curl and check both places. JevDev#52 doesn't touch this script, so it needs its own change.

### Medium: `check_install.py` says the Codex write gate never fires, but it does

`check_install.py:167` prints `ok (unavailable here)`, and the README says Codex sends patches through `exec`, so the `apply_patch` matcher never fires. The log for this repo holds 395 Codex write rows dated Oct 16 to Oct 30, all with a `path`, and Jev answered 334 of them.

The rows have no tool field, so I can't say which Codex tool produced them. Fix: retest, correct the cell and the README, and log the tool name on each row.

### Low: manual tools and prototypes are barely used

One `ask_jev_files` run in 15 days means this tool isn't part of how work gets done in this repo. My guess at the reason is that nothing in VistaMobileBE's `AGENTS.md` or `.claude/` mentions Jev. Fixing that takes a change in VistaMobileBE, not here.

On the JevDev side, decide whether to ship or park each of `skill_router`, `fixture_curator`, `handoff_check` and `test_escrow`. Add any you ship to `check_install.py`, which doesn't track them today. The open [JevDev#48](https://github.com/z0rd0n88/JevDev/pull/48) routing fix, [JevDev#15](https://github.com/z0rd0n88/JevDev/pull/15) roadmap doc and [JevDev#12](https://github.com/z0rd0n88/JevDev/pull/12) Decision Drift Radar belong in the same decision. I didn't review their contents.

### Low: hook logs record tokens but not cost

Rows carry `input_tokens` and no cost, so I can't price the 28.1M tokens above. Fix: log an estimated cost per row, as `skill_router.py` already does for its own results.

## How I measured this

- **Hook usage:** aggregates of `~/.local/state/jevdev/sentinel.jsonl` and `compact.jsonl`. A row counts for this repo when `repo` or `cwd` contains `VistaMobileBE`. Hooks kept logging during the audit, so totals taken at different moments differ by a few rows.
- **Manual usage:** regex matches on `Skill` and `Bash` tool calls in 1,433 Claude transcripts from VistaMobileBE project directories, excluding this audit's session.
- **Jev references in the repo:** a case-insensitive search of VistaMobileBE. The only real mention is a pointer to JevDev#52 in one handoff doc.

## Not covered

- Manual Jev use from Codex or agy, because I scanned only Claude transcripts.
- `settings.local.json`, which the secrets guard blocks.
- Use from any repo other than VistaMobileBE, except where a figure says "all repos".
- Accuracy of any Jev verdict, since no rows were labeled.
- Raw log rows are deliberately left out of this document, because they can contain commands and instructions.

## Checks to rerun

```bash
python3 ~/JevDev/check_install.py --scope user
```

```bash
jev-selfcheck
```

```bash
for t in ~/JevDev/tests/test_*.py; do python3 "$t" >/dev/null 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
```
