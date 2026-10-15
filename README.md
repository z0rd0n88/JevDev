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

`scope_sentinel.py` asks Jev whether a proposed agent action is `covered`, `ambiguous`, or in `conflict` with the user's latest instruction. `demo_scope_sentinel.sh` runs three example cases through the CLI.

The project's Claude `PreToolUse` hook runs it in shadow mode, and only when `SCOPE_SENTINEL=1` is set in Claude's environment. It never blocks a command. For risky Bash commands (pushes, commits, PR create/merge/close, destructive git/gh/rm/find), it starts a detached judge and returns immediately. The judge sends the redacted command and the latest typed prompt (each clipped to about 2000 characters) to the Jev provider, then appends one row to `.local/sentinel.jsonl`, which is created with mode 0600. Both project Claude hooks run through `with_jev_key.sh`, which loads only `TYPESAFE_API_KEY`/`OPENROUTER_API_KEY` from your secrets file, so the Jev key does not need to be in Claude's environment and no other secret reaches repo code. Rows with an `error` field show missed verdicts, such as a missing key. Label logged rows before choosing any blocking threshold.

Codex runs the same shadow hook from `.codex/config.toml` (`scope_sentinel.py hook codex`), which turns itself on and loads the Jev key the same way. It reads the typed text from the rollout's `UserMessage` items, drops Codex desktop's ambient browser context, and logs rows with `"host": "codex"`. Codex runs project hooks only after you trust them: open Codex in this repo and choose "Trust all and continue", or review them in `/hooks`. Re-trust after any change to the hook commands.

Antigravity (`agy`) runs it from `.agents/hooks.json` (`scope_sentinel.py hook agy`) on `run_command` tool calls, with the same Jev key loading. It reads the `<USER_REQUEST>` block of the latest `USER_INPUT` step in the conversation transcript and logs rows with `"host": "agy"`. `agy` loads this project hooks file without a trust prompt. The skill router has no `agy` host yet.

```bash
python3 tests/test_sentinel.py
```
