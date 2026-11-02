# JevDev agent instructions

## Repository scope

JevDev is the private source repository for JEV-related code, prototypes, and experiments. Keep reusable source, tests, documentation, and reviewed authored fixtures here. A prototype is not an installed Claude or Codex integration; change host configuration only when the user requests installation.

## Changes

Make tracked changes on a non-`main` feature branch in a dedicated worktree and submit them through a pull request. Stage the exact intended files, including deletions, and verify the staged paths before committing. Run `bash check.sh` before pushing; CI runs the same lint and tests. Preserve unrelated work in other checkouts and configuration repositories.

## Credentials and data

Read API credentials from the environment. Never commit credential values, `~/.secrets`, private session transcripts, sampled prompt pools, logs, downloaded YouTube transcripts (e.g., from `yteval` in `docs/reports/`), or live benchmark observations. Keep local run output under ignored `.local/`. Redacting secrets: use `redaction.py`; `CODING_STANDARDS.md` says which view. Review authored fixtures before committing them.

## Routing and evaluation

Discover each host's live skill roster when routing. Record the host, model, router version, and roster hash with observations; do not combine measurements from different snapshots. Score Claude and Codex separately, using the same labeled prompts for baseline, routed, and oracle arms within each host. Label prompts before inspecting observed loads. Do not present an authored pilot as an estimate of real-world accuracy or infer accuracy from a smoke test.

See `README.md` for host-specific preflights and benchmark commands.

## Agent skills

### Issue tracker

GitHub issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Default triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout. See `docs/agents/domain.md`.
