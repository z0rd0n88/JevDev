# jev-pruner

Runtime copy of [`tamaratran/jev-pruner`](https://github.com/tamaratran/jev-pruner) at commit `edbc60262a5edc07e18d646c1a3f8a9f0ae868c5` (MIT, see `LICENSE`). Usage is in the JevDev `README.md`. Compare against that exact commit and re-run the security review before taking any upstream change.

## Kept from upstream

`hooks/fast-jev-output.ts`, `src/jev.ts`, `src/output.ts`, `src/retention.ts`, `src/secrets.ts`, `.claude-plugin/plugin.json`, and the tests in `tests/` for that code. Upstream's Codex wrapper, evals, training, demo, login skills, and npm packaging are not here.

## Changed from upstream

| Change | Where | Review item |
|---|---|---|
| Hardcoded the OpenRouter URL and `jev-latest`; removed the `baseUrl`, `apiKey`, and `model` options | `src/jev.ts`, `.claude-plugin/plugin.json` | HIGH-4 |
| Key comes from `with_jev_key.sh` in an empty environment with `HOME` from the passwd file, and must start with `sk-or-` | `hooks/fast-jev-output.ts` | HIGH-4, H-1 |
| A secret in the command or output skips scoring and archiving | `hooks/fast-jev-output.ts` | HIGH-1 |
| Detector uses `scope_sentinel.py`'s patterns, plus a bare PEM header, a token as a URL's user name, wallet keys, more key names and token prefixes, and a quoted flag value | `src/secrets.ts` | HIGH-2, S-1 |
| Removed conversation history; leading injected tag blocks are stripped, a message with a secret in its first 4,000 characters is dropped, and the rest are clipped to 500 | `src/output.ts`, `hooks/fast-jev-output.ts` | HIGH-3 |
| Replaced `\s*` after `^` with `[ \t]*`; rewrote the four quadratic retention patterns; added a 1,000,000-character cap and a 60 s scoring budget | `src/retention.ts`, `hooks/fast-jev-output.ts` | MEDIUM-1, M-1 |
| Protected `fatal:`, `command not found`, `No such file or directory`, and `denied`, `refused` or `timed out` at a line's end | `src/retention.ts` | M-4 |
| Archive moved out of the project to `pruner/` under the passwd home's `.local/state/jevdev/`; refuses a symlinked state dir; rejects unsafe tool ids | `hooks/fast-jev-output.ts` | MEDIUM-3 |
| Diagnostics on and written to the debug log; failures log their HTTP status; the first failure of each kind (no key, no archive folder, hook error) in a session also prints one transcript line | `hooks/fast-jev-output.ts` | MEDIUM-2, M-4 |
| Removed `userConfig`, so a project's `pluginConfigs` cannot change the defaults | `.claude-plugin/plugin.json` | L-3 |
| No scoring request goes out once the 60 s budget has passed | `hooks/fast-jev-output.ts` | L-1 |
| Raised the drop floor from 0.1 to 0.2, calibrated on OpenRouter Jev: stock Jev scores most noise just above 0.1, so upstream's floor dropped almost nothing; needed chunks scored 0.42 or more | `src/retention.ts` | calibration 2026-11-02 |
| Protected test failures (`FAIL`, `not ok`, nonzero failure counts), `make` errors, `npm ERR!`, Rust `error[E...]`, `Failed to`, crashes and resource exhaustion, merge conflicts and rejected pushes | `src/retention.ts` | floor review M1 |
| Kept `stderr` when pruning persisted output: there it holds host notices that are in no file | `hooks/fast-jev-output.ts` | L-3 of the first review |
| Persisted output is trimmed to `persistedMaxChars` (8,000) instead of core's ~2,200-character preview, which no trim fit, so every persisted output was left untrimmed (`budget_unfit`) | `hooks/fast-jev-output.ts` | debug-log audit 2026-11-12 |
| Tests run on `claude plugin test` through `tests/kit.ts` instead of vitest; removed the tests for history | `tests/` | npm audit |

## What the detector misses

`src/secrets.ts` is a denylist, so an unlisted shape is sent. Known misses: a bare mnemonic, a 32-byte base58 key (same shape as a public key), a Solana key as a JSON byte array, 64 hex characters without `0x`, a Discord bot token with no key name, `('API_KEY', 'x')`, `"token" => "x"`, a bare `AUTH=`, a space-separated `token abc`, `<token>x</token>`, `token%3Dx`, and commands such as `compgen -e`, `cat /proc/self/environ`, `ps eww`, `aws configure list`, and `gh auth status`. A `0x` + 64 hex value or an 87-88 character base58 value always skips pruning, including transaction hashes and signatures.
