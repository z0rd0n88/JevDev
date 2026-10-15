# JevDev

Private source repository for Jev experiments, prototypes, and developer tooling. The first project is a skill-router prototype for Claude Code and Codex. It suggests one skill from each host's live roster and measures whether that suggestion changes the first skill the host loads. It does not install a hook or alter either host's configuration.

## Skill router

The router uses two Jev requests when the initial gate finds a possible skill fit. The first request ranks the live skill roster in balanced Choice shards; the second checks a short list against fuller descriptions. It returns no suggestion when the gate or fit check abstains. Results include the roster hash, router version, provider token count, estimated Jev cost, and routing time.

Prerequisites: Python 3, `PyYAML`, the [local Jev CLI](https://docs.typesafe.ai/cookbooks/skill_suggestion), and the `claude` or `codex` CLI for the host being measured. The default Jev executable is `~/.local/bin/jev`; set `JEV_BIN` to use another path. Set `OPENROUTER_API_KEY` or `TYPESAFE_API_KEY` in your environment without committing it. `CLAUDE_CONFIG_DIR` and `CODEX_HOME` override the default `~/.claude` and `~/.codex` locations.

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

The project's Claude `PreToolUse` hook runs it in shadow mode, and only when `SCOPE_SENTINEL=1` is set in Claude's environment. It never blocks a command and prints nothing. It judges **every** Bash command, not only risky ones: it starts a detached judge and returns immediately. The old `is_risky` regex no longer filters; its result is logged as `risky` so the regex can be scored against Jev. The judge sends a JSON state (`instruction`, `constraints`, `command`, `cwd`; redacted, each clipped to about 2000 characters) to the Jev provider, then appends one row to `.local/sentinel.jsonl`, which is created with mode 0600. Rows carry `sentinel_version` `shadow-v4`; do not mix them with `shadow-v3` rows (text state, `scope` only). Both project Claude hooks run through `with_jev_key.sh`, which loads only `TYPESAFE_API_KEY`/`OPENROUTER_API_KEY` from your secrets file, so the Jev key does not need to be in Claude's environment and no other secret reaches repo code. The `AGENTS.md`, `CLAUDE.md` and `GEMINI.md` of the repo the command runs in (`repo`, the git toplevel of the event `cwd`, not the directory of the script; deduplicated, redacted, clipped) go to Jev as the constraints, and each row lists them in `constraint_files`. At most four judges run at once; a fifth command logs a `skipped` error row instead of calling Jev. Rows with an `error` field show missed verdicts, such as a missing key.

Each row has `host`, `host_model`, `model` (requested), `jev_model` (from the response), `gate` (`bash`), `cwd`, `repo`, `risky`, `effect`, `effect_confidence`, `destructive_intent`, `would_block`, and `block_reason`, plus the older `result`, `confidence`, `instruction`, `command`, `constraint_files`, `elapsed`, `input_tokens`. `would_block` is what a live gate would have done (irreversible effect at confidence 0.6 or more, or destructive intent 0.7 or more); nothing acts on it yet. Label logged rows before choosing any blocking threshold.

Live smoke: `bash smoke.sh claude bash` runs one canned prompt through Claude and prints the newest matching row as `host=… host_model=… jev_model=… gate=… would_block=…`. `bash smoke.sh <host> <feature> --read` prints the newest row without running the host. Codex cannot run headless with project hooks; `smoke.sh codex …` prints the manual steps. Other host/feature pairs are wired in later phases.

Codex runs the same shadow hook from `.codex/config.toml` (`scope_sentinel.py hook codex`), which turns itself on and loads the Jev key the same way. It reads the typed text from the rollout's `UserMessage` items, drops Codex desktop's ambient browser context, and logs rows with `"host": "codex"`. Codex runs project hooks only after you trust them: open Codex in this repo and choose "Trust all and continue", or review them in `/hooks`. Re-trust after any change to the hook commands.

Antigravity (`agy`) runs it from `.agents/hooks.json` (`scope_sentinel.py hook agy`) on `run_command` tool calls, with the same Jev key loading. It reads the `<USER_REQUEST>` block of the latest `USER_INPUT` step in the conversation transcript and logs rows with `"host": "agy"`. `agy` loads this project hooks file without a trust prompt. The skill router has no `agy` host yet.

```bash
python3 tests/test_sentinel.py
```

## Skills

`hyper-jev` is the upstream [ten-levels-of-jev](https://github.com/disler/ten-levels-of-jev) skill at commit `777adaf`, vendored unedited under `.agents/skills/hyper-jev/` (MIT; upstream `LICENSE` sits beside `SKILL.md`). One copy serves all hosts:

| Host | Loads from | Invoke |
|---|---|---|
| Claude Code | `.claude/skills/hyper-jev` (symlink to the `.agents` copy) | `/hyper-jev <request>` |
| Codex | `.agents/skills/hyper-jev` | `$hyper-jev <request>`; `/skills` lists it |
| agy | `.agents/skills/hyper-jev` | `/hyper-jev <request>` |

The skill's `$ARGUMENTS` placeholder is filled by Claude's slash form; Codex and agy pass the rest of the prompt as ordinary text, so state the request in the same message. `templates/` (the TypeScript starter) is inert reference material: nothing here runs it. Smoke: `bash smoke.sh <claude|agy|codex> skill` asks the host for the Purpose line (Codex prints manual steps).
