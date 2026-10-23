## Summary

Codex routing failed open because its roster parser rejected skill descriptions.
Agy had no routing adapter or compaction advice. All three hosts now use native
hook contracts, active roster discovery, shared Jev transport, and installation
checks. The repository instructions require three-host support for every feature.

```text
Claude/Codex UserPromptSubmit -> live roster -> Jev -> native hint
Agy PreInvocation -> local /skills snapshot -> Jev -> injectSteps
Agy PostInvocation -> reported token usage -> compaction advice
```

## Evidence

- **Before:** regression cases failed for current Codex roster lines, absent Agy
  routing/benchmark support, and omitted installer/checker entries.
  **After:** all 12 offline Python suites pass, including nine router regression
  cases, the localhost HTTP contract, and the incoming Test Intent Escrow suite.
- Live roster discovery passed in Claude Code, Agy, and Codex. Agy discovery uses
  its zero-turn local command, retaining native names and excluding manual-only
  skills. Benchmark observations remain separate by host, model, and roster.
- Ruff passes for touched Python files; smoke shell syntax and git whitespace
  checks pass. New authored fixtures stay separate from live observations.
- Provider-backed routing and UI receipt of hints were not exercised: this shell
  inherits no Jev key. No user/global host settings were installed or changed.

## Merge Danger

**Door:** two-way

**Blast Radius:** hooks

Advice stays non-blocking. Agy uses PostInvocation for compaction because a Stop
message would restart execution. Codex users must review the edited hook commands
in `/hooks` before interactive validation. The install checker reports wiring and
presence of trust entries; it does not prove hook execution or re-approve hashes.
