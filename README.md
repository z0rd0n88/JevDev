# JevDev

Private source repository for Jev experiments, prototypes, and developer tooling. Jev is TypeSafe's System One model: it answers typed questions (a yes/no probability, a choice, or a score) about a piece of state. The tools here use it to route skills, judge shell commands and file writes, advise on compaction, check handoffs and reviews, and trim Bash output. They run as project hooks in Claude Code, Codex, and Antigravity (`agy`), as CLIs, or as libraries. No hook blocks a prompt, a command, or a write: the gates log in shadow mode, and the router and advisor only suggest.

## Features

| Feature | Entry point | Runs as | Hosts |
|---|---|---|---|
| [Jev CLI](#jev-cli) | `bin/jev`, `bin/jev-selfcheck` | shell CLI | any |
| [Jev from Python](#jev-from-python) | `jev_patterns.py`, `redaction.py` | library | any |
| [Skill router](#skill-router) | `skill_router.py`, `skill_router_agy.py` | `UserPromptSubmit` hook, CLI | Claude, Codex (agy wrapper not wired) |
| [Authored pilot](#authored-pilot) | `benchmarks/`, `fixture_curator.py` | CLI | Claude, Codex |
| [Scope Sentinel](#scope-sentinel) (bash and write gates) | `scope_sentinel.py` | `PreToolUse` hook, CLI | Claude, Codex, agy |
| [Compaction advisor](#compaction-advisor) | `compact_advisor.py` | `Stop` hook | Claude, Codex |
| [File questions](#ask_jev_filespy-cli) | `ask_jev_files.py` | CLI | any |
| [Decision Drift Radar](#decision-drift-radar) | `drift_radar.py` | CLI | any |
| [Handoff integrity check](#handoff-integrity-check) | `handoff_check.py` | CLI | any |
| [Test intent escrow](#test-intent-escrow) | `test_escrow.py` | CLI | any |
| [Finding triage](#finding-triage) | `finding_triage.py`, `corpus_findings.py`, `calibrate_findings.py` | library, CLIs | offline |
| [Skills](#skills) | `hyper-jev`, `ask-jev` | agent skills | Claude, Codex, agy |
| [Bash output pruner](#bash-output-pruner) | `pruner/` | Claude Code mod | Claude |
| [Workflow router](#workflow-router) | `vendor/workflow-router/`, `vendor_sync.py` | CLI (hook not wired) | Claude |
| [Install check](#install-check), [user-scope install](#user-scope-install) | `check_install.py`, `install_user.py` | CLI | Claude, Codex, agy |
| [Smoke tests](#smoke-tests), [checks](#development) | `smoke.sh`, `check.sh`, CI | shell | any |

## Setup

- Python 3.11 or later (`tomllib`, `enum.StrEnum`; CI uses 3.12), `PyYAML` (`python3 -m pip install PyYAML`), `jq`, and `curl` 7.76+ (for `--fail-with-body`).
- A Jev key in `TYPESAFE_API_KEY` or `OPENROUTER_API_KEY`. Never commit it. The hooks read it from `~/.secrets` through `with_jev_key.sh`, so it does not need to be in the host's environment.
- The `jev` CLI at `~/.local/bin/jev`. Link this repo's copy: `mkdir -p ~/.local/bin && ln -s "$PWD/bin/jev" ~/.local/bin/jev`. A copy made with `install -m 755` (as `bin/jev`'s header says) also works, but `install_user.py` refuses to run while a regular file sits at that path. The copy previously installed at `~/.local/bin/jev` put the API key on curl's command line; replace it. `JEV_BIN` points the Python tools at another `jev`.
- The `claude` or `codex` CLI for the host you measure or hook.
- Environment overrides: `CLAUDE_CONFIG_DIR` and `CODEX_HOME` (default `~/.claude` and `~/.codex`); `GEMINI_HOME` for the agy router wrapper (default `~/.gemini`); `JEV_MODEL` (default `jev-latest`); `JEV_LOG_DIR` for the sentinel and advisor logs (default `$CLAUDE_PROJECT_DIR/.local`, else `.local` beside the scripts).

## Project hooks

Opening this repo in a host turns these hooks on. Every hook command runs through `with_jev_key.sh`, which loads only `TYPESAFE_API_KEY` and `OPENROUTER_API_KEY` from `~/.secrets` and then runs the command, so no other secret reaches repo code. The sentinel runs only when `SCOPE_SENTINEL=1`; `.claude/settings.json` sets it in `env`, and the Codex and agy commands set it inline.

| Event | Script | Claude (`.claude/settings.json`) | Codex (`.codex/config.toml`) | agy (`.agents/hooks.json`) |
|---|---|---|---|---|
| `UserPromptSubmit` | `skill_router.py hook` | yes (90 s timeout) | yes (90 s timeout) | no |
| `PreToolUse` | `scope_sentinel.py hook` | `Bash`; `Write`, `Edit`, `NotebookEdit` | `Bash`; `apply_patch` | `run_command`; `write_to_file`, `replace_file_content`, `multi_replace_file_content` |
| `Stop` | `compact_advisor.py hook` | yes | yes | no |

Codex runs project hooks only after you trust them: open `codex` in this repo and choose "Trust all and continue", or review them in `/hooks`. Codex marks an edited hook command as untrusted, so re-trust after pulling a change to one. agy loads `.agents/hooks.json` without a trust prompt.

## Jev CLI

`bin/jev` asks Jev one question from the shell. The state is the second argument, or stdin.

```bash
jev 'Does this request a refund?' 'I want my money back'
git log -1 --format=%B | jev 'Is this a breaking change?'
jev -c billing,technical,sales 'Which team handles this?' "$(cat ticket.txt)"
jev -s Calm,Frustrated,Angry 'How frustrated is the customer?' <<<"$msg"
```

- Question types: noul (the default, a yes/no probability), `-c a,b,c` (choice), `-s l0,l1,l2` (score, 2 to 10 levels), and `-q '<json>'` (a raw questions object, for per-label descriptions).
- Options: `-m MODEL` (default `jev-latest`), `-j` (print the full JSON response), `-n` (dry run: print the request body and route, send nothing, no key needed), `-h`.
- Exit status: for noul, 0 when the probability is at least 0.5 and 1 below it; 2 on an HTTP failure; 64 on a usage error or a refused base URL; 78 when no key is set.
- The key prefix picks the route: `sk-or-` goes to `https://openrouter.ai/api`, `vck_` to `https://ai-gateway.vercel.sh/typesafe`, and anything else to `https://api.typesafe.ai`. `JEV_BASE_URL` may only restate the key's route or a path below it. A loopback URL also needs `JEV_ALLOW_LOCAL=1` and is sent no key.
- curl reads the auth header from stdin and the body from fd 3, so neither is on curl's argv (the question, `-q` JSON, and a positional state are on `jev`'s own argv). curl gives up after 30 s.

`bin/jev-selfcheck` checks whichever `jev` is first on `PATH`, offline with a fake curl: request bodies for every question type, stdin and object state, key-prefix routing, refused base URLs, no key sent to a local route, and exit 78 without a key. It exits 1 on any failure.

```bash
python3 tests/test_jev_cli.py
```

## Jev from Python

`jev_patterns.py` is the only Python module that runs `jev`. `scope_sentinel.py`, `skill_router.py`, `compact_advisor.py`, `ask_jev_files.py`, `drift_radar.py`, `handoff_check.py`, `test_escrow.py`, `fixture_curator.py`, and `finding_triage.py` import it; `skill_router_agy.py` and `calibrate_findings.py` reach it through `skill_router` and `finding_triage`. The pruner calls OpenRouter from TypeScript and does not use it.

- `call(state, questions, *, job, model=None, timeout=40.0, redacted=False)` runs `jev` once with the state on stdin (a `str` verbatim, anything else as JSON) and returns the parsed response plus `elapsed`. It runs `jev -m <model> -q <questions> -j -- <job>`: `-j` is the bare full-JSON flag, `--` ends the options (so a job starting with `-` is not read as a flag), and `job` only fills `jev`'s required `<question>` positional, which `-q` mode ignores. The job is not sent to the provider or logged; it shows only in `jev`'s argv. It redacts the state with `redaction.redact_state()` first unless the caller passes `redacted=True`; `tests/test_redaction.py` lists the callers allowed to.
- The child gets an isolated environment (`PATH`, `HOME`, `USER`, `SYSTEMROOT`, `TMPDIR`, `JEV_BASE_URL`, `JEV_ALLOW_LOCAL`, the proxy and CA settings `HTTPS_PROXY`, `https_proxy`, `NO_PROXY`, `no_proxy`, `CURL_CA_BUNDLE`, `SSL_CERT_FILE`, and one Jev key), so `GH_TOKEN` and other secrets never reach it. Proxy settings are forwarded so `curl` inside `jev` works behind a proxy with its own CA, such as a corporate proxy or a Claude Code cloud session. A proxy URL can carry credentials (`user:pass@host`); `jev` needs it to reach the provider, so it is forwarded anyway.
- Every transport or envelope failure raises `JevError`. Its message never contains `jev`'s stderr; the first non-empty stderr line (at most 200 characters) is on `.stderr` and the exit status on `.returncode`.
- Helpers: `has_key()`; `model_name()`, which reads `JEV_MODEL` (default `jev-latest`) and passes it as `-m`, never through the environment; `input_tokens()`; and `estimated_usd()` at $0.042 per million input tokens. `JEV_BIN` is read once, at import.

`redaction.py` is the one place secret patterns live, in two views. `redact()` is for text a judge reads: a value stops at statement punctuation, so code cannot hide behind a redacted value. `redact_strict()` is for text read only for its content, and fails closed. Both hide the value after any name containing `token`, `secret`, `password`, `passwd`, `api_key`, or `private_key` (including harmless ones such as `max_tokens=1024`), and known token shapes: GitHub and GitLab tokens, `sk-`, `ts_`, `vck_`, Hugging Face and npm tokens, Google and AWS keys, Slack tokens, JWTs, `Authorization:` and `Bearer` values, URL userinfo, `curl -u user:pass`, and PEM private keys. `CODING_STANDARDS.md` says which view to use, and any change to `SECRETS` bumps `SENTINEL_VERSION`.

Tests run a stub `jev` on `JEV_BIN`:

```bash
python3 tests/test_jev_patterns.py
python3 tests/test_redaction.py
```

## Skill router

The router uses two Jev requests when the initial gate finds a possible skill fit. The first request ranks the live skill roster in balanced Choice shards; the second checks a short list against fuller descriptions. It returns no suggestion when the gate or fit check abstains. Results include the roster hash, router version, provider token count, estimated Jev cost, and routing time.

```bash
python3 skill_router.py --host claude measure
python3 skill_router.py --host codex measure
python3 skill_router.py --host claude route 'Help me create a reusable skill.'
python3 skill_router.py --host codex route 'Help me create a reusable skill.'
python3 skill_router.py --host claude sample .local/sample-claude.jsonl [--transcripts DIR] [--count 300] [--per-session 3]
python3 tests/test_router.py
```

- `measure` discovers the host-visible roster without a Jev call, but it still calls the host CLI: on Claude, `claude -p "Say OK." --model haiku --max-budget-usd 0.10` and `claude plugin list --json`; on Codex, `codex debug prompt-input`. `route`, `benchmark`, and `hook` repeat that discovery on every call.
- `route` sends one request's text to Jev.
- `hook` is the project `UserPromptSubmit` hook. It reads the prompt from stdin and, when the router suggests a skill, adds the suggestion to the host's context. Any error fails open with a `systemMessage`.
- `sample` reads local session files (default `$CLAUDE_CONFIG_DIR/projects` or `$CODEX_HOME/sessions`) and writes candidate prompts of 50 to 1,000 characters; it does not upload transcript files. Its pattern filter is only a first pass, so review every sampled prompt before using it in a live benchmark.

`skill_router.py` has no agy host; `skill_router_agy.py` wraps the same router for agy: `python3 skill_router_agy.py {measure | route REQUEST | hook}`. It discovers skills under `$GEMINI_HOME` (`config/skills`, `antigravity-cli/skills`, `antigravity-cli/builtin/skills`, and `config/plugins/*/skills/*/SKILL.md`), and `hook` answers an agy `PreInvocation` event with an `ephemeralMessage`, failing open. Nothing wires it in, and no test covers it.

### category-v1

`--router category-v1` routes through the fixed categories in `catalog/categories.yaml`. `balanced-shards-v2` stays the default for `route`, `hook` and `benchmark`.

1. **Request 1** asks the three gate questions plus one Choice over about 15 categories, using each category's written criteria. A gate below `GATE_THRESHOLD` stops here, so an abstention costs only this small request.
2. **Request 2** runs only over the chosen category's pool. The pool adds the runner-up category when that scores at least `SECOND_CATEGORY`. It asks `which` plus `fits::<skill>` for each member, using descriptions clipped to `DESC_LIMIT`. A pool larger than `POOL_LIMIT` is trimmed in code first, by an inverse-frequency ranker over names and descriptions.
3. **Fallback.** If the top category scores below `CATEGORY_FLOOR`, the router reruns as `balanced-shards-v2`, adds those requests to the totals and records `fallback: true`. It does the same when Jev picks `other` while live skills are uncategorized.

`--router category-nogate-v2` is the same router without the gate. Request 1 asks only the category Choice. A confident `other` (at least `CATEGORY_FLOOR`) abstains. An unsure answer widens the pool to the top two non-`other` categories instead of falling back. Uncategorized skills join every pool. The `fits` check in request 2 alone decides whether anything is suggested, and asks whether each skill improves the execution of the request rather than whether it can do it. (v1 asked the old question; on 30 routine file edits it routed 19.)

`catalog/catalog.yaml` covers `my-skills` (as the `my-skills:` plugin), loose `~/.claude/skills`, parked `skills/disabled` and `agents-parked` from ClaudeConfig, project-only agents, four public local plugins and the cloud-synced roster. It gives each skill:

- a category, plus optional `also` categories;
- an `action`: `prompt`, `session` or `agent`;
- an `invoke` value. Only `auto` entries are routed: `user` marks skills that must not self-trigger, `internal` marks subagents spawned by another skill, and `"off"` mirrors `skillOverrides`.

Agents carry `kind: agent` and sit in their own namespace, so a skill and an agent can share a name. Each agent lists the repos whose `.claude/agents` hold a copy in `projects`. With `--roster live`, routing reads only the host's roster, so parked skills and agents are never picked. Library mode (below) routes them too.

Live skills missing from the catalog get a keyword-rule category, and are reported as uncategorized when no single category clearly leads. Results add `categories`, `chosen_categories`, `pool`, `fallback` and `catalog_sha256`. Editing the catalog changes routing as much as changing the roster does, so start a new observations file.

```bash
python3 skill_router.py --host claude catalog
python3 skill_router.py --host claude --router category-v1 route 'Find why this total is wrong.'
python3 tests/test_skill_catalog.py
python3 tests/test_router_category.py
```

### Library mode (no live roster)

`--roster library` makes the router choose from the whole catalog, so nothing needs to sit in the host's skill listing. Each routable catalog entry resolves to its file through the path templates in `catalog/library.yaml`: parked skills, agents, and `my-skills` from its checkout. The router then deploys only its pick, as a hint that names the file. A skill hint reads "read that file and follow it"; an agent hint says to run the file's instructions as a subagent. `JEV_LIBRARY` points at another templates file.

```bash
python3 skill_router.py --roster library catalog
python3 skill_router.py --roster library --router category-v1 route 'Find why this total is wrong.'
python3 skill_router.py --host claude --roster library --router category-v1 hook
```

A library-mode benchmark runs every Claude arm with no skills (`--disable-slash-commands`), no plugin MCP servers (`--strict-mcp-config`) and only `Read`. The library directories are not added to the session, so the agent learns a file's location only from the hint. A load is the first turn reading a library file. The baseline arm therefore measures a bare agent, and the routed and oracle arms measure what one routed file adds. `score` also reports `wrong_loads_accepting_alternatives`, which counts a row's labeled same-job `alternatives` as right. With every parked skill available, near-duplicates such as `diagnosing-bugs` and `my-skills:addyosmani-debugging-and-error-recovery` compete.

`catalog` reports coverage of the live roster without a Jev call. It lists skills tagged by rule, skills left uncategorized, catalog entries missing from the roster, pool sizes, and the size of request 1. Tag every uncategorized skill in `catalog.yaml` before you benchmark.

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
python3 skill_router.py --host claude --router category-v1 benchmark benchmarks/pilot-labels-claude.jsonl .local/pilot-observations-claude-category-v1.jsonl --reuse-arms .local/pilot-observations-claude.jsonl
python3 skill_router.py --host claude score .local/pilot-observations-claude-category-v1.jsonl
```

Compare `category-v1` with `balanced-shards-v2` only when both observation files share a roster hash. Each router needs its own observations file.

`--reuse-arms` copies the baseline and oracle loads from another router's observations instead of rerunning them. Neither arm sees the router's suggestion, so a second router costs 100 agent sessions instead of 300. The source file must match the host, agent model, roster hash and labels, or the run stops before any session starts. Copied rows record `arms_reused_from`, and `score` counts them as `rows_with_reused_arms`. Both routers then share the same baseline and oracle samples, so their `routed` results are compared against identical controls.

`benchmarks/pilot-labels-claude-2026-11.jsonl` is a draft remap of the Claude labels to the November 2026 roster. It keeps the same prompts and IDs. The original gold skills are gone: `ClaudesMods` was split into `my-skills` and `ThinkTime`, and `superpowers` is disabled. So each covered row now records `previous_gold`, `remap` (`rename` or `substitute`), `remap_confidence` and any `alternatives`. The four substitutes are judgment calls; review them before you run:

- **`ClaudesMods:prd`**, high confidence.
- **`superpowers:systematic-debugging`**, high confidence.
- **`superpowers:brainstorming`**, medium confidence.
- **`superpowers:test-driven-development`**, ambiguous: `tdd` and `my-skills:addyosmani-test-driven-development` overlap.

Each prompt runs in three fresh agent sessions: baseline, Jev suggestion, and gold-label suggestion. Claude's first `Skill` call and Codex's first observed `SKILL.md` read count as loads. Covered prompts count as wrong when the first load differs from the label; uncovered prompts count as needless when any skill loads. The observations file checkpoints after routing and each arm, so the same command resumes interrupted work. A changed roster, router version, host, or agent model requires a new observations file.

`benchmark` requires at least 100 label rows, each with `label_method` `blind_manual`, a non-empty `label_reason`, and the matching host, including uncovered rows. `--model` overrides the agent model and `--limit N` runs the first N prompts. The full pilot invokes up to 300 agent sessions per host and can take hours. Claude defaults to `haiku` with a $0.10 cap per agent call; Codex defaults to `gpt-6-luna`. The host prompts are not identical: Claude receives a system-prompt addition, while Codex receives a delimited addition to the user turn. Compare arms within a host. Keep credentials, sampled transcripts, logs, and live observations out of Git; `.local/` is ignored.

`python3 fixture_curator.py FILE.jsonl [--skip-jev]` checks a fixture file. It first checks structure: every row a JSON object with non-empty `id` and `text`, `gold` a string or null, and no duplicate ids. Unless `--skip-jev` is given, it then asks Jev about each row and flags prompts that are not self-contained (below 0.5) and gold-labeled prompts where several skills are defensible (0.5 or more). It exits 1 on a structural error or a Jev failure; flags alone exit 0. It does not check the `label_method` and `label_reason` fields that `benchmark` requires.

```bash
python3 tests/test_fixture_curator.py
```

## Scope Sentinel

`scope_sentinel.py` asks Jev about a Bash command in one call with three questions: `scope` (`covered`, `ambiguous`, or `conflict` against the user's latest instruction and the repo's constraints), `effect` (`read_only`, `reversible`, `irreversible`), and `destructive_intent` (a probability).

```bash
python3 scope_sentinel.py --instruction TEXT --action CMD [--constraints TEXT] [--json]
bash demo_scope_sentinel.sh
```

The CLI judges one command and prints the scope, effect, destructive intent, would-block verdict, time, and tokens, with a warning unless the scope is `covered`; `--json` prints the full verdict. `demo_scope_sentinel.sh` runs three example cases (covered, ambiguous, conflict) through the CLI. It makes live Jev calls and needs the key in the environment.

As a hook it runs in shadow mode: it never blocks a command and prints nothing. It judges every Bash command, not only risky ones: it starts a detached judge and returns immediately. The old `is_risky` regex no longer filters; its result is logged as `risky` so the regex can be scored against Jev. The judge sends a JSON state (`instruction`, `constraints`, `command`, `cwd`; the first three redacted and clipped to about 2,000 characters each) to the Jev provider, then appends one row to `sentinel.jsonl` in the log directory (default `.local/`), created with mode 0600. Rows carry `sentinel_version` `shadow-v8`, the version that moved every secret pattern into `redaction.py`; bash rows hold a word-by-word redacted view of the command, with `redacted_hits`, `scan_unreliable`, `hidden_operator`, and `clipped`. Do not mix them with older rows: `shadow-v4` to `shadow-v7` used older redaction, and `shadow-v3` rows have a text state and `scope` only. The `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` of the repo the command runs in (`repo`, the git toplevel of the event `cwd`, not the directory of the script; deduplicated, redacted, clipped) go to Jev as the constraints, and each row lists them in `constraint_files`. At most four judges run at once; a fifth command logs a `skipped` error row instead of calling Jev. Rows with an `error` field show missed verdicts, such as a missing key; `error` may end with ` | <redacted first jev stderr line>`.

Each row has `sentinel_version`, `ts`, `session_id`, `host`, `host_model`, `model` (requested), `jev_model` (from the response), `gate` (`bash`), `tool` (the host's tool name), `cwd`, `repo`, `risky`, `effect`, `effect_confidence`, `destructive_intent`, `would_block`, and `block_reason`, plus the older `result`, `confidence`, `instruction`, `command`, `constraint_files`, `elapsed`, `input_tokens`, and `estimated_usd` (also on write and advisor rows). `would_block` is what a live gate would have done (irreversible effect at confidence 0.6 or more, or destructive intent 0.7 or more); nothing acts on it yet. Label logged rows before choosing any blocking threshold. A row with no user instruction (`error` `no user instruction found in transcript`) is never a block: it is logged with `error` and counted separately when a blocking threshold is chosen.

Codex runs it as `scope_sentinel.py hook codex`. It reads the typed text from the rollout's `UserMessage` items, drops Codex desktop's ambient browser context (a subagent's rollout has no typed text, so it reads the rollout named by `session_meta.parent_thread_id`), and logs rows with `"host": "codex"`.

agy runs it as `scope_sentinel.py hook agy` on `run_command` tool calls. It reads the `<USER_REQUEST>` block of the latest `USER_INPUT` step in the conversation transcript (a subagent's transcript has none, so it reads the conversation that sent its `invoke_subagent` message) and logs rows with `"host": "agy"`.

### Write gate

The same shadow hook also judges file writes, in one Jev call with two questions: `kind` (`source_code`, `config`, `secrets`, `docs`, `data`) and `contains_secret` (a probability). A path outside the repo, or the repo root itself, is marked `would_block` locally with `outside the repo: <path>` and never reaches Jev; the exception is the session's own Claude scratchpad (and a repo that lives inside it is judged normally), which is logged with `scope` `scratchpad`, no `would_block`, and no Jev call. Content is redacted before Jev sees it (first 4,000 characters) and is never logged; rows carry `gate` `write`, `tool`, `estimated_usd`, the repo-relative `path`, `kind`, `kind_confidence`, `contains_secret`, `redacted_hits`, `would_block`, `block_reason`. `would_block` means a credential at 0.7 or more, or a `secrets` file at 0.8 or more. Nothing acts on it yet.

| Host | Tools (hook matcher) | Config |
|---|---|---|
| Claude Code | `Write`, `Edit`, `NotebookEdit` (`Edit` sends `new_string`, which may be a fragment) | `.claude/settings.json` |
| Codex | `apply_patch` (path from the first `*** Add/Update/Delete File:` header) | `.codex/config.toml` |
| agy | `write_to_file`, `replace_file_content`, `multi_replace_file_content` | `.agents/hooks.json` |

A Codex `apply_patch` with no `*** Add/Update/Delete File:` header logs a row with `path` null and `skipped` `no patch header`, without calling Jev. The Codex write gate fires on Codex's native `apply_patch` tool (the VistaMobileBE log held 395 Codex write rows between Oct 16 and Oct 30, 2026).

```bash
python3 tests/test_sentinel.py
```

## Compaction advisor

`compact_advisor.py` is a `Stop` hook (Claude and Codex) that asks Jev, once per turn and only above the notice line, whether this is a good moment to compact. It prints `{"systemMessage": …}` for you to read, or nothing; it never compacts for you and never blocks. A `Stop` hook is synchronous, so a stalled provider can delay the prompt by up to 40 s once. Four questions over a JSON state (`current_request`, `previous_work` = the 20 most recent earlier prompts, `recent_turn`, `tools_this_turn`): `switched_gears`, `at_boundary`, `needs_history`, `mid_operation`.

It stays `silent` (logged, not printed) when `mid_operation` is above 0.6, or unless `switched_gears` is above 0.7 or `at_boundary` is above 0.6 with a `needs_history` score below 1. Otherwise the token count picks the tier: `notice` below the recommend line, then `recommend`, then `request`.

| Host | Token source | Window |
|---|---|---|
| Claude | last main-chain assistant `message.usage`: input + cache creation + cache read + output | unknown, so no percentage |
| Codex | last `token_count` event, `last_token_usage.total_tokens` | `model_context_window` |
| agy | unavailable: not wired (no usage, no compact action) | |

Lines are absolute tokens: 80,000 (notice), 110,000 (recommend), 160,000 (request). Override with `JEV_COMPACT_LINES=notice,recommend,request`; raise them for a 1M-window model. Below the notice line, or on the first request, no Jev call is made. Rows go to `compact.jsonl` in the log directory with `tier`, `reason`, `tokens`, `window`, `answers`, `printed`, and `error`, plus `host`, `host_model`, `advisor_version`, `model`, `jev_model`, `ts`, `session_id`, `cwd`, `repo`, `lines`, `elapsed`, `input_tokens`, and `estimated_usd`.

```bash
python3 tests/test_compact.py
```

## ask_jev_files.py CLI

`ask_jev_files.py` asks Jev typed questions about files, one chosen file, or one situation, and prints JSON, so an agent branches on numbers without reading the files. Whole files only (no chunking). It runs from any repo: "the repo" is the git toplevel of the current directory, and paths in the output are repo-relative. From another repo, call it by its path in the JevDev checkout (the `ask-jev` skill uses `/home/alex/Projects/jev-dev`).

```
python3 /home/alex/Projects/jev-dev/ask_jev_files.py files [-r] -q QUESTIONS_JSON PATH_OR_GLOB...
python3 /home/alex/Projects/jev-dev/ask_jev_files.py pick  -q QUESTION_TEXT PATH...
python3 /home/alex/Projects/jev-dev/ask_jev_files.py ask   -q QUESTIONS_JSON [--state TEXT] [--paths P...] [--command CMD]
```

Every subcommand takes `--model` (default `JEV_MODEL`, else `jev-latest`).

- `files` runs one Jev call per file (16 at a time) and returns `results` sorted by path, `skipped` with a reason each, `calls`, and `model`. A directory without `-r` (`--recursive`) means `dir/*` (dotfiles excluded); up to 255 files, each under 240,000 bytes. It skips empty files, binary files (a known binary extension, or a NUL byte in the first 8 KiB), `.lock` files, files under `node_modules`, `.git`, `.sessions`, `dist`, `build`, `coverage`, `.pi`, `.local`, or `__pycache__`, and paths outside the repo.
- `pick` chooses one of the paths you give it (no expansion, at most 254 candidates) and returns `path`, `confidence`, `probabilities`, and `skipped`; `path` is null when Jev says `none` or is under 0.3 confident.
- `ask` judges one situation from your own `--state` (up to 8,000 characters), up to 20 `--paths` files (expanded recursively), and the output of `--command`. The command is judged first by the live bash gate and never runs when blocked; a command over 2,000 characters or not readable as shell is blocked without a Jev call. It runs in the repo root under `/bin/bash` with `CI=1` and a 60 s timeout, and each of stdout and stderr is clipped to 200,000 characters. Each gate decision is logged to `sentinel.jsonl` (`host` `cli`, `source` `ask_jev_files`) under `JEV_LOG_DIR` or `<repo>/.local`. Over 60,000 tokens it refuses and prints a `split`; nothing is truncated.

Questions are validated before any file is read: a choice needs 1 to 255 criteria keys, and a score needs a list of 2 to 10 levels. Recursive then pick: `files -r -q '<one noul question>' .` fans out over a tree, keep the paths whose answer clears your bar, then `pick -q '<question>' <those paths>` chooses one.

Exit codes: 0 ok; 2 refused or failed (stdout is `{"error": …}`); 64 usage error; 78 no Jev key (`TYPESAFE_API_KEY` or `OPENROUTER_API_KEY`; run through `with_jev_key.sh`). When Jev fails, the reason is the first line of `jev`'s stderr with secrets redacted (for example `jev: HTTP 429 rate limited`), or the library's safe message when there is none.

```bash
python3 tests/test_ask_jev_files.py
```

## Decision Drift Radar

`drift_radar.py` asks Jev whether a diff implements, contradicts, leaves unaddressed, or defers one recorded owner decision, or is too thin to tell (`unclear`). `defers` flags a diff that fills in something the owner explicitly deferred. The diff (a file up to 1 MB, text only) is redacted with `redaction.redact()` before it is sent and framed as untrusted data. Redaction is greedy, so the output reports how many values were hidden and a gate can treat a non-zero count as needing a human look. Verdicts are review leads, not approvals.

```
python3 drift_radar.py --decision TEXT --diff PATH [--json] [--fail-on-drift] [--allow-unclear] [--min-confidence F] [--model M] [--timeout S]
```

`--json` prints `result`, `confidence`, `elapsed`, `input_tokens`, `redacted` (values hidden from the judge) and `warning` (the review-required text, or `null`); the same warning is also printed to stderr in both modes. `redacted` is informational and never fails the run.

Exit codes: 0 ok. With `--fail-on-drift`: 2 on `contradicts`, `unaddressed`, or `defers`; then 3 on `unclear` unless `--allow-unclear`; then 2 when `confidence` is below `--min-confidence` (default 0.0, off). 1 on any error, including no Jev key, an empty decision or diff, and a Jev answer whose choice or confidence is invalid or whose choice is not the most probable entry of its `probabilities`; 64 usage error; 130 on Ctrl-C. When Jev fails, stderr carries the first line of `jev`'s stderr with secrets redacted, or the library's safe message when there is none.

```bash
python3 tests/test_drift_radar.py
```

## Handoff integrity check

`handoff_check.py` checks a handoff against a decision ledger in one Jev call, grading each ledger item `intact`, `missing`, `falsely_complete`, or `changed`.

```
python3 handoff_check.py --ledger PATH --handoff PATH [--model M] [--timeout S] [--json] [--strict]
```

Each non-empty ledger line that does not start with `#` is one item (a leading `- ` or `* ` is dropped; at most 50 items). Both files must be at most 2 MB and not symlinks. The handoff is redacted and clipped to 25,000 characters. The timeout defaults to 40 s. `--json` prints `elapsed`, `input_tokens`, `total_items`, `violations_count`, and `results` (`line`, `item`, `verdict`, `confidence` per item). Exit codes: 0 when every item is intact; 1 on a violation or any error; 2 on a violation with `--strict`.

```bash
python3 tests/test_handoff_check.py
```

## Test intent escrow

`python3 test_escrow.py --diff PATH` asks whether an edited test assertion still `protects` the behavior it stated, was `weakened`, or is `unrelated`. It prints the verdict, confidence, time, and tokens, with a warning on `weakened`. It exits 0 on any verdict, including `weakened`, and 1 on error.

```bash
python3 tests/test_test_escrow.py
```

## Finding triage

`finding_triage.py` is a library that grades review findings. It parses review reports (and finding-fixer output) into findings and builds each finding's state: the redacted cited hunk with 15 lines of context, its `git blame` age, the share of lines the PR wrote, and prior-round findings. Per finding, Jev answers `introduced_by_this_diff`, `duplicate_of_prior_round`, `severity`, and `fix_is_mechanical`; per round, `round_materially_same_as_previous` and a `keystone` choice. A review loop has converged when the round is materially the same as the last one and adds no new finding of HIGH severity or worse. Every threshold is 0.85. It is not wired into a review skill yet.

`corpus_findings.py` builds the findings corpus from a repo's merged PRs, one row per PR, round, and finding. It reads review reports posted as PR comments, saved under `docs/reviews` or `.claude/reviews` in the checkout, or found in Claude and Codex transcripts that name the PR. It needs an authenticated `gh` and `git`, makes no Jev calls, and caches redacted raw text under `.local/raw` (directory 0700, files 0600).

```bash
python3 corpus_findings.py --limit 15            # the 15 latest merged PRs
python3 corpus_findings.py --pr 1110             # one PR
```

Other flags: `--repo-slug` (default `VistaMarkets/VistaMobileBE`), `--checkout` (default `~/VistaMobileBE`), `--out` (default `.local/findings-corpus.jsonl`), `--no-transcripts`, and `--refresh` (refetch cached PR data).

`calibrate_findings.py` replays the corpus through `finding_triage` and reports how Jev's labels agree with the record: hand labels from `tests/fixtures/findings/labels-pr<N>-r<K>.json` where a row has one, else a title-match proxy, plus blame.

```bash
bash with_jev_key.sh python3 calibrate_findings.py            # every row in .local/findings-corpus.jsonl
bash with_jev_key.sh python3 calibrate_findings.py --pr 1110  # one PR, written to .local/calibration-pr1110.jsonl
python3 calibrate_findings.py --from-graded                   # re-cut the report from --out, no Jev calls
```

Other flags: `--corpus`, `--checkout`, `--model`, and `--out` (default `.local/calibration.jsonl`). The results are in `docs/reports/2026-10-31-finding-triage-calibration.md`.

```bash
python3 tests/test_finding_triage.py
```

## Skills

`hyper-jev` is the upstream [ten-levels-of-jev](https://github.com/disler/ten-levels-of-jev) skill at commit `777adaf`, vendored unedited under `.agents/skills/hyper-jev/` (MIT; upstream `LICENSE` sits beside `SKILL.md`). It ships a `cookbook/` of guides and use cases, and `templates/` (a TypeScript starter) as inert reference material: nothing here runs it. One copy serves all hosts:

| Host | Loads from | Invoke |
|---|---|---|
| Claude Code | `.claude/skills/hyper-jev` (symlink to the `.agents` copy) | `/hyper-jev <request>` |
| Codex | `.agents/skills/hyper-jev` | `$hyper-jev <request>`; `/skills` lists it |
| agy | `.agents/skills/hyper-jev` | `/hyper-jev <request>` |

The skill's `$ARGUMENTS` placeholder is filled by Claude's slash form; Codex and agy pass the rest of the prompt as ordinary text, so state the request in the same message.

`ask-jev` is authored here (`.agents/skills/ask-jev/SKILL.md`, with the same `.claude/skills` symlink) and documents `ask_jev_files.py`: the three subcommands, the three question types, and three runnable recipes (triage a failure, judge a diff, classify a request). It loads the same way as `hyper-jev`: `/ask-jev <request>` in Claude and agy, `$ask-jev <request>` in Codex.

```bash
python3 tests/test_hyper_jev.py
python3 tests/test_ask_jev_skill.py
```

## Upstream levels 1 to 5

Upstream levels 1 to 5 (ten-levels-of-jev `README.md`, commit `777adaf`) are plain functions over one client. Here the client is `jev_patterns.call`, and each level lives in the function that already does that job.

| Level | Upstream option | Here |
|---|---|---|
| 1. Single Decisions | B (urgency gate) | `compact_advisor.decide_tier` checks the `mid_operation` Noul first and stays silent when it is `> 0.6`. |
| 2. Multiple Choice | A (support triage) | `scope_sentinel.BASH_QUESTIONS` asks a Choice (`effect`) and a Noul (`destructive_intent`) about one command in a single call, and `gate_bash` decides which answers matter. |
| 3. Composite Scoring | A (ticket priority) | `skill_router.suggest` averages the three `GATES` answers in code (inverting `prose_suffices`) and stops after one request when the average is below `GATE_THRESHOLD`. |
| 4. Confidence Gating | A (bash tool gate) | `gate_bash` blocks an `irreversible` pick only when its confidence clears `BASH_THRESHOLDS["irreversible"]`, or when `destructive_intent` clears `BASH_THRESHOLDS["destructive"]`. |
| 5. Intent and Model Routing | A (agent router) | `skill_router.suggest` routes in two requests, a wide sharded Choice then a fit check on the shortlist, and suggests a skill only when its fit is at least `FITS_THRESHOLD`. |

New callers import `jev_patterns.call` and keep their thresholds in code, never in the prompt.

## Bash output pruner

`pruner/` is a Claude Code mod that trims Bash output over 3,000 estimated tokens (about 10,500 characters) before the model reads it. Jev scores 20-line chunks through OpenRouter, and low-scoring chunks become `[N lines omitted]` markers. Failed commands, binary output, and documents such as diffs and JSON pass through whole. It is a pinned copy of [`tamaratran/jev-pruner`](https://github.com/tamaratran/jev-pruner); [`pruner/README.md`](pruner/README.md) records the commit and every change from upstream.

- **What leaves the machine:** the command, the output chunks, and the last three user messages, with leading injected tag blocks removed, any message that matches a secret pattern dropped, and the rest clipped to 500 characters each. Conversation history is not sent. The secret patterns are a denylist, so an unlisted shape is sent; [`pruner/README.md`](pruner/README.md) names the known misses.
- **Skipped without a call:** a command or output that matches the secret patterns, output past 1,000,000 characters, a missing `OPENROUTER_API_KEY`, or a key without the `sk-or-` prefix. Each returns the original result. So does a failed or late scoring call (60 s budget).
- **The full output:** saved to `~/.local/state/jevdev/pruner/`, outside every repo, and named in the footer. Files there are not deleted automatically. `~/.local/state/jevdev` must already exist as a real directory (`install_user.py` creates it); otherwise the output is left untrimmed. Output that Claude has already persisted to a file is trimmed to 8,000 characters at its existing path instead.
- **Key:** read from your secrets file through `with_jev_key.sh`, in an empty environment with `HOME` from the passwd file, so a project's `env` cannot substitute another account. A key set only in Claude's environment is ignored here. The mod finds `with_jev_key.sh` beside `pruner/`, so it must load from inside the JevDev checkout.
- **Logs:** each decision goes to the debug log as counts only, with no command or output text. Read it with `claude --debug`. The first output of each kind in a session that cannot be trimmed (no key, no archive folder, a hook error) also prints one dim transcript line, which the model does not see.
- **Hosts:** Claude only. Codex would need `sandbox_workspace_write.network_access=true`, which opens the network to every sandboxed command.

Tests need no npm install and make no network calls:

```bash
claude plugin validate pruner
claude plugin test pruner
```

## Workflow router

`vendor/workflow-router/` is an exact copy of the `workflow-router` skill from [`z0rd0n88/my-skills`](https://github.com/z0rd0n88/my-skills) (`skills/workflow-router/`). The skill picks a workflow for a task; its `hooks/jev_route.py` asks Jev three questions in one call (which process workflow the prompt starts in, whether the user asked for a multi-agent workflow, and how well the work suits one) and can run as a `UserPromptSubmit` hook that suggests a route. The questions and the gate table in that script restate the skill's rules, so the script lives inside the skill and my-skills is the only place either is edited. The whole skill folder is copied so the script's case files and the documents it points to come with it.

```bash
bash with_jev_key.sh python3 vendor/workflow-router/hooks/jev_route.py ask 'Bump React from 17 to 19.'
bash with_jev_key.sh python3 vendor/workflow-router/hooks/jev_route.py eval vendor/workflow-router/evals/process-judge/cases.jsonl process
```

- **Not installed.** No hook config in this repo runs `jev_route.py`, and the copy is not under `.agents/skills/`, so no host loads the skill from here. [`vendor/workflow-router/hooks/README.md`](vendor/workflow-router/hooks/README.md) has the settings snippet and says what the hook sends.
- **Outside this repo's rules for its own code.** `jev_route.py` calls Jev with `curl` and has its own short secret-pattern list, because it has to run from a skill folder with no JevDev module beside it. It does not go through `jev_patterns.call()` or `redaction.py`, and `ruff.toml` excludes `vendor/` so a lint fix cannot become a local edit.
- **The copy cannot be edited here.** `vendor/workflow-router.lock.json` records the my-skills commit, the skill folder's git tree id, and each file's sha256 and mode. `python3 vendor_sync.py check` compares the copy with the lock, offline; `tests/test_vendor_sync.py` runs it, so `bash check.sh` and CI fail on a hand edit, an added or missing file, or a changed executable bit. Files git ignores (the judges' `out-*/` run output) are skipped.
- **A change in my-skills shows up as stale.** `python3 vendor_sync.py check --source <my-skills checkout>` also compares the lock with that checkout's committed files. `.github/workflows/vendor-drift.yml` runs it against my-skills' default branch every Monday, on demand, and on pull requests that touch `vendor/`. my-skills is private, so the workflow needs a repository secret `MY_SKILLS_READ_TOKEN` (a fine-grained token with read access to that repo's contents); without it the job prints a warning and compares nothing.
- **Updating.** `python3 vendor_sync.py sync --source <my-skills checkout>` replaces the copy with the checkout's committed files and rewrites the lock. It refuses a checkout with uncommitted changes under the skill. Commit the copy and the lock together.

```bash
python3 vendor_sync.py check
python3 vendor_sync.py check --source ../my-skills
python3 vendor_sync.py sync --source ../my-skills
python3 tests/test_vendor_sync.py
```

## Smoke tests

`smoke.sh` runs one canned prompt in a host, then prints the newest matching log row (`host=… host_model=… jev_model=… gate=… would_block=…`).

```bash
bash smoke.sh <claude|codex|agy> <bash|write|compact|ask|ask-skill|skill> [--read] [--user]
```

| Feature | What the host does | Claude, agy | Codex |
|---|---|---|---|
| `bash` | runs `ls -la` | runs headless, prints the bash-gate row | prints manual steps |
| `write` | writes and deletes `smoke-note.txt` with its file tool | runs headless, prints the write-gate row | prints manual steps |
| `compact` | two prompts on different topics, interactively | Claude prints the interactive steps; agy has no advisor | prints the interactive steps |
| `ask` | runs `ask_jev_files.py ask` with the triage question over `python3 tests/test_sentinel.py` | runs headless, prints the host's bash-gate row for that command | prints manual steps |
| `ask-skill` | `/ask-jev` triages `python3 tests/test_sentinel.py` | shows the reply, which names a `kind` with a confidence, then the row | prints manual steps |
| `skill` | `/hyper-jev` replies with its Purpose line | shows the reply | prints manual steps |

`--read` prints the newest row for that host and feature without running the host. `--user` checks the user-scope install from another repo (`bash smoke.sh <claude|agy> bash --user` runs from `/home/alex/Projects/BotHaus`).

## Install check

`python3 check_install.py` prints a feature × host table showing whether each feature is wired at project scope. It only reads configs; it never edits them or trusts a Codex hook. `--root PATH` and `--home PATH` override the repo and home directories; `--scope user` reads the user-scope files instead (`~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.gemini/config/hooks.json`, the three user skill dirs) and first prints `jevdev checkout: <branch> @ <sha>`. The skill-router hook has no row.

| Cell | Meaning |
|---|---|
| `ok` | wired (and, for Codex hooks, trusted) |
| `n/a (unavailable)` | the host has no such feature (agy compaction advisor, the pruner outside Claude) |
| `n/a (user scope only)` | the pruner loads from `~/.claude/settings.json` alone; read it with `--scope user` |
| `missing` | config absent, malformed, or lacking the entry; exit code 1 |
| `untrusted` | Codex has no `hooks.state` trust entry for the hook in `~/.codex/config.toml`; trust it in `codex` via `/hooks`. Alone it keeps exit code 0 |

```bash
python3 tests/test_check_install.py
```

## User-scope install

Runs the gates, advisor, and skills in every repo on this machine from the primary checkout, logging to `~/.local/state/jevdev/`. The skill router is not installed at user scope. In `--user` mode, each hook stands down in a repo whose project config already runs that same script, so no double rows.

1. `python3 install_user.py` (idempotent; `--home` and `--jevdev` override the defaults, `--remove` deletes what it owns). It merges `~/.codex/hooks.json`, writes the `jevdev` hook in `~/.gemini/config/hooks.json`, links the two skills into `~/.agents/skills` and `~/.gemini/antigravity-cli/skills`, links `jev` and `jev-selfcheck` into `~/.local/bin`, creates `~/.local/state/jevdev`, and prints the Claude snippet. A real file or directory at a link path is refused (exit 2) and nothing changes, so move an existing `~/.local/bin/jev` copy aside first.
2. Claude: open a ClaudeConfig PR with the printed snippet (`~/.claude/settings.json` hooks, the `CLAUDE_CODE_PLUGIN_DIRS` entry that loads `pruner/`, two `Edit` deny rules for `pruner/` and `with_jev_key.sh`, plus two `ln -s` lines for the Claude skill links). Merge and pull it while no Claude session runs; running sessions rewrite that file.
3. Codex: open `codex` anywhere and trust the new hooks in `/hooks`.
4. After every merge here: `git -C ~/Projects/jev-dev pull` (the hooks run that checkout; keep it on `main`).
5. Check: `python3 check_install.py --scope user` and `jev-selfcheck`. Live smoke: `bash smoke.sh <claude|agy> bash --user`.

```bash
python3 tests/test_install_user.py
```

## Development

`bash check.sh` runs every check CI runs: `ruff check .`, then each `tests/test_*.py` in its own process (several point `JEV_BIN` at a stub before importing). It prints `ok` or `FAIL` per file, with the last 20 lines of a failure, and exits 1 on any failure. CI (`.github/workflows/checks.yml`) runs it on every pull request and on pushes to `main`, with Python 3.12, `ruff==0.15.12`, and PyYAML. `AGENTS.md` asks for `bash check.sh` before every push.

```bash
bash check.sh
python3 tests/test_<name>.py     # one test file
```

## Docs

- `docs/agents/`: issue tracker, triage-label, and domain-doc conventions that `AGENTS.md` points to.
- `docs/audit/`: the 2026-10-30 VistaMobileBE Jev usage audit.
- `docs/ideas/`: idea notes, feature opportunities, and the smart-reader postmortem. Its AST-slicing recommendation is superseded: whole-file questions (`ask_jev_files.py`) replaced `ast_symbol_ranker.py`, which was removed.
- `docs/reports/`: the finding-triage calibration report.
- `docs/specs/`: `jev-patterns-library.md` (the design of `jev_patterns.py`) and `ten-levels-port.md`.
- `docs/superpowers/plans/`: the audit-fixes plan.
