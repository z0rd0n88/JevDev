# JevDev

Private source repository for Jev experiments, prototypes, and developer tooling. The first project is a skill-router prototype for Claude Code and Codex. It suggests one skill from each host's live roster and measures whether that suggestion changes the first skill the host loads. It does not install a hook or alter either host's configuration.

## Skill router

The router uses two Jev requests when the initial gate finds a possible skill fit. The first request ranks the live skill roster in balanced Choice shards; the second checks a short list against fuller descriptions. It returns no suggestion when the gate or fit check abstains. Results include the roster hash, router version, provider token count, estimated Jev cost, and routing time.

Prerequisites: Python 3, `PyYAML`, `jq`, `curl` 7.76+ (for `--fail-with-body`), the local Jev CLI (install this repo's copy: `mkdir -p ~/.local/bin && install -m 755 bin/jev ~/.local/bin/jev`; the copy previously installed at `~/.local/bin/jev` put the API key on curl's command line), and the `claude` or `codex` CLI for the host being measured. The default Jev executable is `~/.local/bin/jev`; set `JEV_BIN` to use another path. Set `OPENROUTER_API_KEY` or `TYPESAFE_API_KEY` in your environment without committing it. `CLAUDE_CONFIG_DIR` and `CODEX_HOME` override the default `~/.claude` and `~/.codex` locations.

```bash
python3 -m pip install PyYAML
python3 skill_router.py --host claude measure
python3 skill_router.py --host codex measure
python3 skill_router.py --host claude route 'Help me create a reusable skill.'
python3 skill_router.py --host codex route 'Help me create a reusable skill.'
python3 tests/test_router.py
```

`measure` discovers the host-visible roster without a Jev call. `route` sends one request's text to Jev. The transcript sampler reads local session files and writes candidate prompts; it does not upload transcript files. Its pattern filter is only a first pass, so review every sampled prompt before using it in a live benchmark.

## Authored pilot

`benchmarks/pilot-labels-claude.jsonl` and `benchmarks/pilot-labels-codex.jsonl` each contain 100 self-contained, manually authored prompts: 60 with skill labels and 40 labeled `null`. Labels were fixed before agent observations. These fixtures exercise the routing and measurement protocol; results from them do not estimate accuracy on ordinary user requests. The two hosts use separate live rosters, labels, observations, and scores.

```bash
mkdir -p .local
python3 skill_router.py --host claude benchmark benchmarks/pilot-labels-claude.jsonl .local/pilot-observations-claude.jsonl --limit 1
python3 skill_router.py --host codex benchmark benchmarks/pilot-labels-codex.jsonl .local/pilot-observations-codex.jsonl --limit 1
python3 skill_router.py --host claude benchmark benchmarks/pilot-labels-claude.jsonl .local/pilot-observations-claude.jsonl
python3 skill_router.py --host codex benchmark benchmarks/pilot-labels-codex.jsonl .local/pilot-observations-codex.jsonl
python3 skill_router.py --host claude score .local/pilot-observations-claude.jsonl
python3 skill_router.py --host codex score .local/pilot-observations-codex.jsonl
```

Each prompt runs in three fresh agent sessions: baseline, Jev suggestion, and gold-label suggestion. Claude's first `Skill` call and Codex's first observed `SKILL.md` read count as loads. Covered prompts count as wrong when the first load differs from the label; uncovered prompts count as needless when any skill loads. The observations file checkpoints after routing and each arm, so the same command resumes interrupted work. A changed roster, router version, host, or agent model requires a new observations file.

The full pilot invokes up to 300 agent sessions per host and can take hours. Claude defaults to `haiku` with a $0.10 cap per agent call; Codex defaults to `gpt-6-luna`. The host prompts are not identical: Claude receives a system-prompt addition, while Codex receives a delimited addition to the user turn. Compare arms within a host. Keep credentials, sampled transcripts, logs, and live observations out of Git; `.local/` is ignored.

## Scope Sentinel

`scope_sentinel.py` asks Jev about a Bash command in one call with three questions: `scope` (`covered`, `ambiguous`, or `conflict` against the user's latest instruction and the repo's constraints), `effect` (`read_only`, `reversible`, `irreversible`), and `destructive_intent` (a probability). `demo_scope_sentinel.sh` runs three example cases through the CLI, which also prints the effect and would-block verdict.

The project's Claude `PreToolUse` hook runs it in shadow mode, and only when `SCOPE_SENTINEL=1` is set in Claude's environment. It never blocks a command and prints nothing. It judges **every** Bash command, not only risky ones: it starts a detached judge and returns immediately. The old `is_risky` regex no longer filters; its result is logged as `risky` so the regex can be scored against Jev. The judge sends a JSON state (`instruction`, `constraints`, `command`, `cwd`; redacted, each clipped to about 2000 characters) to the Jev provider, then appends one row to `.local/sentinel.jsonl`, which is created with mode 0600. Rows carry `sentinel_version` `shadow-v6` (a secret's punctuation and a value on the next line are hidden); do not mix them with `shadow-v5` or `shadow-v4` rows (older redaction) or `shadow-v3` rows (text state, `scope` only). Both project Claude hooks run through `with_jev_key.sh`, which loads only `TYPESAFE_API_KEY`/`OPENROUTER_API_KEY` from your secrets file, so the Jev key does not need to be in Claude's environment and no other secret reaches repo code. The `AGENTS.md`, `CLAUDE.md` and `GEMINI.md` of the repo the command runs in (`repo`, the git toplevel of the event `cwd`, not the directory of the script; deduplicated, redacted, clipped) go to Jev as the constraints, and each row lists them in `constraint_files`. At most four judges run at once; a fifth command logs a `skipped` error row instead of calling Jev. Rows with an `error` field show missed verdicts, such as a missing key; `error` may end with ` | <redacted first jev stderr line>`.

Each row has `host`, `host_model`, `model` (requested), `jev_model` (from the response), `gate` (`bash`), `tool` (the host's tool name), `cwd`, `repo`, `risky`, `effect`, `effect_confidence`, `destructive_intent`, `would_block`, and `block_reason`, plus the older `result`, `confidence`, `instruction`, `command`, `constraint_files`, `elapsed`, `input_tokens`, and `estimated_usd` (also on write and advisor rows). `would_block` is what a live gate would have done (irreversible effect at confidence 0.6 or more, or destructive intent 0.7 or more); nothing acts on it yet. Label logged rows before choosing any blocking threshold. A row with no user instruction (`error` `no user instruction found in transcript`) is never a block: it is logged with `error` and counted separately when a blocking threshold is chosen.

Live smoke: `bash smoke.sh claude bash` runs one canned prompt through Claude and prints the newest matching row as `host=… host_model=… jev_model=… gate=… would_block=…`. `bash smoke.sh <host> <feature> --read` prints the newest row without running the host. Codex cannot run headless with project hooks; `smoke.sh codex …` prints the manual steps. Other host/feature pairs are wired in later phases.

Codex runs the same shadow hook from `.codex/config.toml` (`scope_sentinel.py hook codex`), which turns itself on and loads the Jev key the same way. It reads the typed text from the rollout's `UserMessage` items, drops Codex desktop's ambient browser context (a subagent's rollout has no typed text, so it reads the rollout named by `session_meta.parent_thread_id`), and logs rows with `"host": "codex"`. Codex runs project hooks only after you trust them: open Codex in this repo and choose "Trust all and continue", or review them in `/hooks`. Re-trust after any change to the hook commands.

Antigravity (`agy`) runs it from `.agents/hooks.json` (`scope_sentinel.py hook agy`) on `run_command` tool calls, with the same Jev key loading. It reads the `<USER_REQUEST>` block of the latest `USER_INPUT` step in the conversation transcript (a subagent's transcript has none, so it reads the conversation that sent its `invoke_subagent` message) and logs rows with `"host": "agy"`. `agy` loads this project hooks file without a trust prompt. The skill router has no `agy` host yet.

### Write gate

The same shadow hook also judges file writes, in one Jev call with two questions: `kind` (`source_code`, `config`, `secrets`, `docs`, `data`) and `contains_secret` (a probability). A path outside the repo, or the repo root itself, is marked `would_block` locally with `outside the repo: <path>` and never reaches Jev; the exception is the session's own Claude scratchpad (and a repo that lives inside it is judged normally), which is logged with `scope` `scratchpad`, no `would_block`, and no Jev call. Content is redacted before Jev sees it (first 4000 characters) and is never logged; rows carry `gate` `write`, `tool`, `estimated_usd`, the repo-relative `path`, `kind`, `kind_confidence`, `contains_secret`, `redacted_hits`, `would_block`, `block_reason`. `would_block` means a credential at 0.7 or more, or a `secrets` file at 0.8 or more. Nothing acts on it yet.

| Host | Tools (hook matcher) | Config |
|---|---|---|
| Claude Code | `Write`, `Edit`, `NotebookEdit` (`Edit` sends `new_string`, which may be a fragment) | `.claude/settings.json` |
| Codex | `apply_patch` (path from the first `*** Add/Update/Delete File:` header) | `.codex/config.toml` |
| agy | `write_to_file`, `replace_file_content`, `multi_replace_file_content` | `.agents/hooks.json` |

A Codex `apply_patch` with no `*** Add/Update/Delete File:` header logs a row with `path` null and `skipped` `no patch header`, without calling Jev.

Codex write gate: wired, and it fires on Codex's native `apply_patch` tool (the VistaMobileBE log held 395 Codex write rows between Oct 16 and Oct 30, 2026). Codex marks an edited hook command as untrusted: re-trust in `/hooks` after pulling this change.

Smoke: `bash smoke.sh claude write`, `bash smoke.sh agy write`, `bash smoke.sh agy bash` run a canned prompt and print the newest matching row. `bash smoke.sh codex bash` prints the manual steps.

```bash
python3 tests/test_sentinel.py
```

`jev_patterns.py` is the only module that runs `jev`; the sentinel, `ask_jev_files.py`, `compact_advisor.py`, `skill_router.py`, `fixture_curator.py`, `handoff_check.py`, `test_escrow.py`, and `drift_radar.py` all go through it: `call(state, questions, job=…)` runs `jev` once with the state on stdin and returns the parsed response plus `elapsed`. The child gets an isolated environment (`PATH`, `HOME`, `USER`, `SYSTEMROOT`, `TMPDIR`, `JEV_BASE_URL`, `JEV_ALLOW_LOCAL`, and one Jev key), so `GH_TOKEN` and other secrets never reach it. Every transport or envelope failure raises `JevError`, whose message never contains `jev`'s stderr (that is on `.stderr`). Tests run a stub `jev` on `JEV_BIN`:

```bash
python3 tests/test_jev_patterns.py
```

## Compaction advisor

`compact_advisor.py` is a `Stop` hook (Claude and Codex) that asks Jev, once per turn and only above the notice line, whether this is a good moment to compact. It prints `{"systemMessage": …}` for you to read, or nothing; it never compacts for you and never blocks. A `Stop` hook is synchronous, so a stalled provider can delay the prompt by up to 40 s once. Four questions over a JSON state (`current_request`, `previous_work` = the 20 most recent earlier prompts, `recent_turn`, `tools_this_turn`): `switched_gears`, `at_boundary`, `needs_history`, `mid_operation`. Tiers: `notice` (below the recommend line), `recommend`, `request`.

| Host | Token source | Window |
|---|---|---|
| Claude | last main-chain assistant `message.usage`: input + cache creation + cache read + output | unknown, so no percentage |
| Codex | last `token_count` event, `last_token_usage.total_tokens` | `model_context_window` |
| agy | unavailable: not wired (no usage, no compact action) | |

Lines are absolute tokens: 80 000 (notice), 110 000 (recommend), 160 000 (request). Override with `JEV_COMPACT_LINES=notice,recommend,request`; a 1M-window model wants higher lines. Below the notice line, or on the first request, no Jev call is made. Rows go to `.local/compact.jsonl` (`tier`, `reason`, `tokens`, `window`, `answers`, `printed`, `error`). Codex runs project hooks only after trust: re-trust in `/hooks`. Manual check: `bash smoke.sh claude compact` or `bash smoke.sh codex compact` prints the interactive steps; add `--read` for the newest row.

```bash
python3 tests/test_compact.py
```

## ask_jev_files.py CLI

`ask_jev_files.py` asks Jev typed questions about files, one chosen file, or one situation, and prints JSON, so an agent branches on numbers without reading the files. Whole files only (no chunking). It runs from any repo: "the repo" is the git toplevel of the current directory, and paths in the output are repo-relative.

```
python3 /home/alex/JevDev/ask_jev_files.py files [-r] -q QUESTIONS_JSON PATH_OR_GLOB...
python3 /home/alex/JevDev/ask_jev_files.py pick  -q QUESTION_TEXT PATH...
python3 /home/alex/JevDev/ask_jev_files.py ask   -q QUESTIONS_JSON [--state TEXT] [--paths P...] [--command CMD]
```

- `files` runs one Jev call per file (16 at a time) and returns `results` sorted by path, `skipped` with a reason each, `calls`, and `model`. A directory without `-r` means `dir/*` (dotfiles excluded); up to 255 files, each under 240 000 bytes. Empty, binary, lock, and `node_modules`-style files are skipped.
- `pick` chooses one of the paths you give it (no expansion) and returns `path`, or null when Jev says `none` or is under 0.3 confident.
- `ask` judges one situation from your own `--state` (up to 8000 chars), up to 20 `--paths` files, and the output of `--command`. The command is judged first by the live bash gate and never runs when blocked; each gate decision is logged to `sentinel.jsonl` (`host` `cli`, `source` `ask_jev_files`) under `JEV_LOG_DIR` or `<repo>/.local`. Over 60 000 tokens it refuses and prints a `split`; nothing is truncated.

Recursive then pick: `files -r -q '<one noul question>' .` fans out over a tree, keep the paths whose answer clears your bar, then `pick -q '<question>' <those paths>` chooses one.

Exit codes: 0 ok; 2 refused or failed (stdout is `{"error": …}`); 64 usage error; 78 no Jev key (`TYPESAFE_API_KEY` or `OPENROUTER_API_KEY`; run through `with_jev_key.sh`). Questions are validated before any file is read. When Jev fails, the reason is the first line of `jev`'s stderr with secrets redacted (for example `jev: HTTP 429 rate limited`), or the library's safe message when there is none.

Smoke: `bash smoke.sh claude ask` and `bash smoke.sh agy ask` have the host run the triage question over `python3 tests/test_sentinel.py`; the host's reply holds the `kind` and `flaky` answers and the script prints the host's sentinel row. Codex: run `codex` here, trust the hooks, send the same prompt, then `bash smoke.sh codex ask --read`.

```bash
python3 tests/test_ask_jev_files.py
```

## Decision Drift Radar

`drift_radar.py` asks Jev whether a diff implements, contradicts, leaves unaddressed, or defers one recorded owner decision, or is too thin to tell (`unclear`). `defers` flags a diff that fills in something the owner explicitly deferred. The diff (a file up to 1 MB, text only) is redacted with the Scope Sentinel's secret list before it is sent and framed as untrusted data. Redaction is greedy: any value after a name containing `token`, `secret`, `password` or `api_key` is replaced, including harmless ones such as `max_tokens=1024`, so the output reports how many values were hidden and a gate can treat a non-zero count as needing a human look. Verdicts are review leads, not approvals.

```
python3 drift_radar.py --decision TEXT --diff PATH [--json] [--fail-on-drift] [--allow-unclear] [--min-confidence F] [--model M] [--timeout S]
```

`--json` prints `result`, `confidence`, `elapsed`, `input_tokens`, `redacted` (values hidden from the judge) and `warning` (the review-required text, or `null`); the same warning is also printed to stderr in both modes. `redacted` is informational and never fails the run. Exit codes: 0 ok; with `--fail-on-drift`: 2 on `contradicts`, `unaddressed`, or `defers`, 3 on `unclear` unless `--allow-unclear`, and 2 when `confidence` is below `--min-confidence` whatever the verdict (default 0.0, off); 1 on any error, including no Jev key, an empty decision or diff, and a Jev answer whose choice or confidence is invalid or whose choice is not the most probable entry of its `probabilities`; 64 usage error; 130 on Ctrl-C. When Jev fails, stderr carries the first line of `jev`'s stderr with secrets redacted, or the library's safe message when there is none.

```bash
python3 tests/test_drift_radar.py
```

## Skills

`hyper-jev` is the upstream [ten-levels-of-jev](https://github.com/disler/ten-levels-of-jev) skill at commit `777adaf`, vendored unedited under `.agents/skills/hyper-jev/` (MIT; upstream `LICENSE` sits beside `SKILL.md`). One copy serves all hosts:

| Host | Loads from | Invoke |
|---|---|---|
| Claude Code | `.claude/skills/hyper-jev` (symlink to the `.agents` copy) | `/hyper-jev <request>` |
| Codex | `.agents/skills/hyper-jev` | `$hyper-jev <request>`; `/skills` lists it |
| agy | `.agents/skills/hyper-jev` | `/hyper-jev <request>` |

The skill's `$ARGUMENTS` placeholder is filled by Claude's slash form; Codex and agy pass the rest of the prompt as ordinary text, so state the request in the same message. `templates/` (the TypeScript starter) is inert reference material: nothing here runs it. Smoke: `bash smoke.sh <claude|agy|codex> skill` asks the host for the Purpose line (Codex prints manual steps).

`ask-jev` is authored here (`.agents/skills/ask-jev/SKILL.md`) and documents `ask_jev_files.py`: the three subcommands, the three question types, and three runnable recipes (triage a failure, judge a diff, classify a request). It loads the same way as `hyper-jev`: `/ask-jev <request>` in Claude and agy, `$ask-jev <request>` in Codex. Smoke: `bash smoke.sh <claude|agy|codex> ask-skill` asks the host to triage `python3 tests/test_sentinel.py`; the reply names a `kind` with a confidence and the script prints the host's `ask_jev_files.py ask` sentinel row (Codex prints manual steps).

## Jev from code

Upstream levels 1 to 5 (ten-levels-of-jev `README.md`, commit `777adaf`) are plain functions over one client. Here the client is `jev_patterns.call`, and each level lives in the function that already does that job.

### Level 1

Single Decisions, option B (urgency gate): `compact_advisor.decide_tier` checks the `mid_operation` Noul first and stays silent when it is `> 0.6`.

### Level 2

Multiple Choice, option A (support triage): `scope_sentinel.BASH_QUESTIONS` asks a Choice (`effect`) and a Noul (`destructive_intent`) about one command in a single call, and `gate_bash` decides which answers matter.

### Level 3

Composite Scoring, option A (ticket priority): `skill_router.suggest` averages the three `GATES` answers in code (inverting `prose_suffices`) and stops after one request when the average is below `GATE_THRESHOLD`.

### Level 4

Confidence Gating, option A (bash tool gate): `gate_bash` blocks an `irreversible` pick only when its confidence clears `BASH_THRESHOLDS["irreversible"]`, or when `destructive_intent` clears `BASH_THRESHOLDS["destructive"]`.

### Level 5

Intent and Model Routing, option A (agent router): `skill_router.suggest` routes in two requests, a wide sharded Choice then a fit check on the shortlist, and suggests a skill only when its fit is at least `FITS_THRESHOLD`.

New callers import `jev_patterns.call` and keep their thresholds in code, never in the prompt.

## Bash output pruner

`pruner/` is a Claude Code mod that trims Bash output over 10,000 estimated tokens before the model reads it. Jev scores 20-line chunks through OpenRouter, and low-scoring chunks become `[N lines omitted]` markers. Failed commands, binary output, and documents such as diffs and JSON pass through whole. It is a pinned copy of [`tamaratran/jev-pruner`](https://github.com/tamaratran/jev-pruner); [`pruner/README.md`](pruner/README.md) records the commit and every change from upstream.

- **What leaves the machine:** the command, the output chunks, and the last three user messages, with leading injected tag blocks removed, redacted, and clipped to 500 characters each. Conversation history is not sent. The secret patterns are a denylist, so an unlisted shape is sent; [`pruner/README.md`](pruner/README.md) names the known misses.
- **Skipped without a call:** a command or output that matches the secret patterns, output past 1,000,000 characters, a missing `OPENROUTER_API_KEY`, or a key without the `sk-or-` prefix. Each returns the original result. So does a failed or late scoring call (60 s budget).
- **The full output:** saved to `~/.local/state/jevdev/pruner/`, outside every repo, and named in the footer. Files there are not deleted automatically.
- **Key:** read from your secrets file through `with_jev_key.sh`, in an empty environment with `HOME` from the passwd file, so a project's `env` cannot substitute another account. A key set only in Claude's environment is ignored here.
- **Logs:** each decision goes to the debug log as counts only, with no command or output text. Read it with `claude --debug`. The first output in a session that cannot be trimmed (no key, no archive folder, a failed call) also prints one dim transcript line, which the model does not see.
- **Hosts:** Claude only. Codex would need `sandbox_workspace_write.network_access=true`, which opens the network to every sandboxed command.

Tests need no npm install and make no network calls:

```bash
claude plugin validate pruner
claude plugin test pruner
```

## Install check

`python3 check_install.py` prints a feature × host table showing whether each feature is wired at project scope. It only reads configs; it never edits them or trusts a Codex hook. `--root PATH` and `--home PATH` override the repo and home directories; `--scope user` reads the user-scope files instead (`~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.gemini/config/hooks.json`, the three user skill dirs).

| Cell | Meaning |
|---|---|
| `ok` | wired (and, for Codex hooks, trusted) |
| `n/a (unavailable)` | the host has no such feature (agy compaction advisor, the pruner outside Claude) |
| `n/a (user scope only)` | the pruner loads from `~/.claude/settings.json` alone; read it with `--scope user` |
| `missing` | config absent, malformed, or lacking the entry; exit code 1 |
| `untrusted` | Codex has no `hooks.state` trust entry for the hook in `~/.codex/config.toml`; trust it in `codex` via `/hooks`. Alone it keeps exit code 0 |

## User-scope install

Runs the gates, advisor, and skills in every repo on this machine from the primary checkout, logging to `~/.local/state/jevdev/`. Repos whose project config already carries `scope_sentinel.py` are skipped by `--user`, so no double rows.

1. `python3 install_user.py` (idempotent; `--home` and `--jevdev` override the defaults). It merges `~/.codex/hooks.json`, writes the `jevdev` hook in `~/.gemini/config/hooks.json`, links the four skills, links `jev` and `jev-selfcheck` into `~/.local/bin` (`bin/jev` lands with JevDev#52, so run the installer after that merge), and prints the Claude snippet. A real file or directory at a skill or `~/.local/bin` path is refused (exit 2); nothing changes. `~/.local/bin/jev` and `jev-selfcheck` must not be regular files when it runs, so move an existing copy aside first.
2. Claude: open a ClaudeConfig PR with the printed snippet (`~/.claude/settings.json` hooks, the `CLAUDE_CODE_PLUGIN_DIRS` entry that loads `pruner/`, plus two `ln -s` lines). Merge and pull it while no Claude session runs; running sessions rewrite that file.
3. Codex: open `codex` anywhere and trust the new hooks in `/hooks`.
4. After every merge here: `git -C ~/JevDev pull` (the hooks run that checkout; keep it on `main`).
5. Check: `python3 check_install.py --scope user` and `jev-selfcheck` (offline; fake curl, no network). Live smoke: `bash smoke.sh <claude|agy> bash --user` (runs from `/home/alex/BotHaus`).

```bash
python3 tests/test_check_install.py
for t in tests/test_*.py; do python3 "$t" || echo "FAIL $t"; done   # full suite
```

`ast_symbol_ranker.py` and its test were removed: whole-file questions (`ask_jev_files.py`) replace AST symbol slicing, so the postmortem's slicing recommendation is superseded.
