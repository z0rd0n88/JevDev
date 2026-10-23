# Three-host Jev compatibility

## Goal
Fix skill routing and make the supported Jev features work with Claude Code,
Antigravity (`agy`), and Codex. Keep host-specific behavior explicit and tested.

## Scope
The user confirmed the 21-file scope on 2026-10-23. Implementation stays on
`fix/three-host-compatibility` in the existing dedicated `features` worktree.
Preserve other worktrees and user configuration. Changes to global host settings
are not part of this work.

## Phases
1. Diagnose failures and capture host contracts: complete.
2. Add failing tests, then implement routing and feature parity: complete.
3. Run the relevant suites, verify live roster discovery, and prepare a PR: complete.

## Decisions
- Routing remains advisory and fails open without disclosing provider errors.
- Discover each host's active roster; ignore disabled plugin caches.
- Use authored fixtures for deterministic tests; keep private transcripts and
  live run output out of Git.
- Check installation reports routing and all supported host integrations.

## Next Step
Publish the prepared PR. After merge, review the updated Codex hooks in /hooks
and run interactive routing smoke checks with an inherited Jev key.

## Errors Encountered
- The existing Codex parser returns an empty roster for descriptions between
  the skill name and file reference.
- The local HTTP router test needs the installed Jev CLI's explicit localhost
  opt-in; this is a test harness issue, separate from roster parsing.
- Context-mode subprocesses do not reliably retain the repository cwd. Use
  absolute paths for analysis and test commands.
