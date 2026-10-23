# Findings

## Confirmed code gaps
- `codex_roster()` accepts only `name: (file: ...)`; the current host includes
  a description before the file reference.
- `host_roster()` dispatches every non-Claude value to Codex. The CLI accepts
  only Claude and Codex, and no Agy router hook is registered.
- The user installer omits routing for every host.
- The install checker omits routing and marks the Agy compaction advisor
  unavailable. The advisor CLI currently accepts only Claude and Codex.

## Host contracts
- Agy's `agy -p /skills --output-format json` is a local command with zero
  model turns. `command.data.skills` supplies exact names, paths, descriptions,
  and `model_invocable`; exclude skills marked false. Do not reconstruct this
  roster from filesystem caches or guess plugin namespaces.
- Agy routing uses PreInvocation with direct handlers and injectSteps output.
  Only a fresh USER_INPUT tail is routed, avoiding repeat calls after tools.
- Agy PLANNER_RESPONSE entries now expose input_tokens, cache_read_tokens, and
  output_tokens. The advisor uses those counts. PostInvocation supports advisory
  injection; Stop can only inject a message by restarting execution, so it is
  unsuitable for non-blocking advice.
- Agy supports /compact as of CLI v1.3.5 (official October 14, 2026 changelog).
- Agy's headless event stream uses event=step_update, not Claude's tool_use schema.
- Antigravity documentation: https://www.antigravity.google/docs/hooks
- Antigravity skill discovery: https://www.antigravity.google/docs/skills
- Existing project host configurations: `.claude/settings.json`,
  `.codex/config.toml`, `.agents/hooks.json`.

## Constraints
- Do not read or source `~/.secrets`, including indirectly through the existing
  key-loading wrapper when running diagnostics.
- Tests use stub Jev executables or localhost with mock credentials.
- Wiring, host execution, and provider behavior are separate validation claims.
