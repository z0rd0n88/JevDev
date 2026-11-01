# jev-pruner

Runtime copy of [`tamaratran/jev-pruner`](https://github.com/tamaratran/jev-pruner) at commit `edbc60262a5edc07e18d646c1a3f8a9f0ae868c5` (MIT, see `LICENSE`). Usage is in the JevDev `README.md`. Compare against that exact commit and re-run the security review before taking any upstream change.

## Kept from upstream

`hooks/fast-jev-output.ts`, `src/jev.ts`, `src/output.ts`, `src/retention.ts`, `src/secrets.ts`, `.claude-plugin/plugin.json`, and the tests in `tests/` for that code. Upstream's Codex wrapper, evals, training, demo, login skills, and npm packaging are not here.

## Changed from upstream

| Change | Where | Review item |
|---|---|---|
| Hardcoded the OpenRouter URL and `jev-latest`; removed the `baseUrl`, `apiKey`, and `model` options | `src/jev.ts`, `.claude-plugin/plugin.json` | HIGH-4 |
| Key comes from `with_jev_key.sh` and must start with `sk-or-` | `hooks/fast-jev-output.ts` | HIGH-4 |
| A secret in the command or output skips scoring and archiving | `hooks/fast-jev-output.ts` | HIGH-1 |
| Detector uses `scope_sentinel.py`'s patterns, plus a bare PEM header and a token as a URL's user name | `src/secrets.ts` | HIGH-2 |
| Removed conversation history; the task string is redacted before clipping | `src/output.ts`, `hooks/fast-jev-output.ts` | HIGH-3 |
| Replaced `\s*` after `^` with `[ \t]*`; added a 4,000,000-character cap and a 60 s scoring budget | `src/retention.ts`, `hooks/fast-jev-output.ts` | MEDIUM-1 |
| Archive moved out of the project to `~/.local/state/jevdev/pruner/`; refuses a symlinked state dir; rejects unsafe tool ids | `hooks/fast-jev-output.ts` | MEDIUM-3 |
| Diagnostics on by default and written to the debug log; failures log their HTTP status | `.claude-plugin/plugin.json`, `hooks/fast-jev-output.ts` | MEDIUM-2 |
| Tests run on `claude plugin test` through `tests/kit.ts` instead of vitest; removed the tests for history | `tests/` | npm audit |
