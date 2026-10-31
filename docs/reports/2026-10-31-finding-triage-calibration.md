# Finding Triage and Convergence, phase 1: corpus and offline calibration

**Date:** 2026-10-31. **Scope:** the 15 most recently merged PRs of `VistaMarkets/VistaMobileBE` (#1054 to #1111), their PR comments, the review records saved in that checkout, and the Claude and Codex transcripts that name them. **Status:** offline only. No review skill, hook, or setting was changed. Thresholds are provisional and live in `finding_triage.py`.

Idea and demand evidence: [`docs/ideas/jev-features-nebula.md`](../ideas/jev-features-nebula.md), Run 3, Safe Pick 1.

## Verdict on the 0.85 thresholds

**Not safe to move into a shadow step yet, on this corpus.** The `duplicate_of_prior_round` question never crossed 0.85 on any of the 25 round-two findings, including the 10 that restate a round-one finding by number, so at 0.85 the label would never fire and the loop would never shorten; the probabilities do separate restated from new findings, but the split sits near 0.5 (precision 0.75, recall 0.60 at 0.5), not 0.85. `introduced_by_this_diff` looks good (precision 0.93, recall 1.00) but the truth proxy is git blame, which is already in the state Jev sees, so that number is mostly Jev reading its input back. The convergence rule is right on the one two-round loop in the corpus (PR 1065 did need a close-out PR), but one loop is not evidence. The corpus is too thin for a go decision: 3 of 15 PRs carried tool reviews, one two-round loop, and zero finding-fixer verdicts anywhere. Next phase should run as a shadow step that only logs, with the duplicate threshold lowered to 0.5 for the log, and should wait for at least five multi-round loops before anything acts on the labels.

## What was built

| File | What it does |
|---|---|
| `finding_triage.py` | Parses the four report shapes the review skills post, builds per-finding state (finding, cited hunk ±15 lines, blame age and share written in the PR, prior-round findings), asks Jev the four per-finding questions plus the per-round `round_materially_same_as_previous` and `keystone` questions through `jev_patterns.call`, labels, and decides convergence. |
| `corpus_findings.py` | Builds `.local/findings-corpus.jsonl`: one row per (PR, round, finding) from PR comments, `docs/reviews` and `.claude/reviews` in the checkout, and Claude + Codex transcripts; orders reports into rounds, merges copies of the same report, joins finding-fixer rulings, marks next-round restatements. Raw bodies cached under `.local/raw`, redacted. |
| `calibrate_findings.py` | Replays the corpus through the grader and prints the numbers below; `--from-graded` re-cuts the report without new Jev calls. |
| `tests/test_finding_triage.py` | Eight offline checks with a stub `jev`: the parser on three real redacted review texts (PR 1110 sweep comment, PR 1063 vista-dw-review comment, PR 1065 saved dw-review), the Multi-Agent Review bucket format, finding-fixer report lines, redaction, grading on a 5-finding fixture (2 duplicates, 1 pre-existing), convergence over 2 rounds. |

## Corpus

Build: `python3 corpus_findings.py --limit 15`. Output, verbatim:

```
PR  1111  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  docs(agents): point judgment calls at Jev
PR  1110  rounds=1  findings=  5  with_verdict=  5  fixer_reports=0  tools=sweep  sources=2  Withdrawals post-merge close-out: review of 391da5
PR  1088  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  chore: withdrawal retro guardrails and ctx live-su
PR  1084  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  ci: enable Gradle build cache, parallel CI build,
PR  1083  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  docs(demo): rewrite the Trade Feed demo guides as
PR  1082  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  fix(gate): guards from the on-ramp retro
PR  1065  rounds=2  findings= 44  with_verdict= 25  fixer_reports=0  tools=dw-review,multi-agent-review  sources=7  Implement gated SOL and USDC withdrawals with priv
PR  1064  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  Timeline
PR  1063  rounds=2  findings=  2  with_verdict=  0  fixer_reports=0  tools=vista-dw-review  sources=4  docs(spec): smoke spec addendum, the signing event
PR  1060  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  docs(demo): real-phone guide for Android and iOS
PR  1059  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  docs(progress): record the deposit merge, the #105
PR  1058  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  docs: refresh living docs against a6f58e57
PR  1057  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  test(accounts): make SolanaRpcWalletBalancePortTes
PR  1056  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  docs(skills): solana-dev triggers on backend JSON-
PR  1054  rounds=0  findings=  0  with_verdict=  0  fixer_reports=0  tools=-  NO TOOL REVIEW FOUND  sources=0  chore: replace the repo big-next-job skill with pr

51 findings, 30 with a skeptic or finding-fixer verdict, 21 orphaned
```

Per source:

| PR | Round | Tool | Primary source | Same report also at | Findings |
|---|---|---|---|---|---|
| 1063 | 1 | vista-dw-review | PR comment by `perseus08`, 2026-10-29 | | 2 (L1, L2, both LOW) |
| 1063 | 2 | multi-agent-review | PR comment by `z0rd0n88`, 2026-10-29 | 3 Codex transcript blocks | 0 ("no supported findings") |
| 1065 | 1 | multi-agent-review | Codex rollout 2026-10-29 (the review ran in Codex; the Claude session holds only a truncated quote) | 2 more copies in the same rollout | 19 (1 CRITICAL, 6 HIGH, 8 MEDIUM, 4 LOW) |
| 1065 | 2 | dw-review | `docs/reviews/2026-10-30-dw-review-391da5d7.md` | | 25 (21 confirmed incl. 2 HIGH, 4 refuted or demoted) |
| 1110 | 1 | sweep (one lane + skeptic) | PR comment by `z0rd0n88`, 2026-10-30 | `docs/reviews/2026-10-30-open-pr-sweep.md` section | 5 (2 DEMOTED, 2 CONFIRMED, 1 REFUTED) |

Twelve PRs had no tool review anywhere: #1111, #1088, #1084, #1083, #1082, #1064, #1060, #1059, #1058, #1057, #1056, #1054. Ten of them are docs, CI, or test-only changes. PR 1065's three comments are an `AC-9.1 withdrawal scan` (ripgrep output), not a review, and were excluded.

Finding-fixer: `finding-fixer` was launched in the PR 1065 session twice, but its per-finding rulings (`F1  fix-here  applied ...`) never appear in any transcript, PR comment, or saved record for these PRs; the only SUPPORTED/REFUTED text in those sessions is the skill's own description. The `fixer` column is therefore empty for every row. The corpus builder parses the Step 5 format and will join rulings when a session keeps them.

Codex and agy: Codex rollouts under `~/.codex/sessions` that name VistaMobileBE were scanned with the same rules; they supplied the PR 1065 round-one report and copies of the PR 1063 report. No agy transcript named the review tools.

Parser failures reported by the build: none on the final run. Two earlier false positives were fixed in code rather than by hand: a changelog-style "what landed" summary with three severity bullets (now requires a `Where:` or `Failure path:` line), and the open-PR sweep record being attached whole to every PR it mentioned (now only its own `## #N:` section counts, and a file with per-PR sections but none for the PR is skipped).

## Calibration

Run: `bash with_jev_key.sh python3 calibrate_findings.py`. Output, verbatim:

```
Rows: 51 findings in 4 rounds across 3 PRs. Jev calls: 56, input tokens: 135793, estimated cost: $0.0057.

- duplicate_of_prior_round at 0.85 (rows with a prior round only): n=25 tp=0 fp=0 fn=10 tn=15 precision=n/a recall=0.00
  - at 0.3: n=25 tp=8 fp=8 fn=2 tn=7 precision=0.50 recall=0.80
  - at 0.4: n=25 tp=6 fp=3 fn=4 tn=12 precision=0.67 recall=0.60
  - at 0.5: n=25 tp=6 fp=2 fn=4 tn=13 precision=0.75 recall=0.60
  - at 0.6: n=25 tp=1 fp=1 fn=9 tn=14 precision=0.50 recall=0.10
  - at 0.7: n=25 tp=1 fp=1 fn=9 tn=14 precision=0.50 recall=0.10
  - duplicate_p per row (restated proxy in brackets): F1=0.56[-], F2=0.20[-], F3=0.40[-], F4=0.56[R], F5=0.54[R], F6=0.53[R], F7=0.57[R], F8=0.80[R], F9=0.34[R], F10=0.02[R], F11=0.08[-], F12=0.39[-], F13=0.27[-], F14=0.36[-], F15=0.15[-], F16=0.29[-], F17=0.17[-], F18=0.29[R], F19=0.71[-], F20=0.34[R], F21=0.56[R], F22=0.38[-], F23=0.32[-], F24=0.33[-], F25=0.03[-]
- introduced_by_this_diff: n=42 tp=38 fp=3 fn=0 tn=1 precision=0.93 recall=1.00
- introduced_by_this_diff vs skeptic 'pre-existing' notes only: n=1 tp=0 fp=1 fn=0 tn=0 precision=0.00 recall=n/a
- severity agrees with the reviewer's stated severity: 14/46; Jev higher: 31, lower: 1
- severity agrees with the skeptic's demoted severity: 0/2
- REFUTED findings graded: 5; of them labelled duplicate 0, pre-existing 0, mechanical 0
- rows with a finding-fixer ruling: 0; mechanical label vs ruling fix-here: n=0 tp=0 fp=0 fn=0 tn=0 precision=n/a recall=n/a
- noted_not_blocking: 0, mechanical: 1, duplicate: 0, pre_existing: 2

## Convergence

- PR 1063: 1 round(s); r1 n=2 new_high=0 same_p=None converged=False keystone=L2
- PR 1065: 2 round(s); r1 n=19 new_high=16 same_p=None converged=False keystone=MINT-1; r2 n=25 new_high=7 same_p=0.1 converged=False keystone=F1
- PR 1110: 1 round(s); r1 n=5 new_high=2 same_p=None converged=False keystone=F2

PRs with 2+ rounds: 1; would have stopped one round earlier under the provisional thresholds: 0.

## Per tool

- dw-review: 25 findings; duplicate 0, pre_existing 1, mechanical 1, mean introduced_p 0.48, mean duplicate_p 0.37
- multi-agent-review: 19 findings; duplicate 0, pre_existing 1, mechanical 0, mean introduced_p 0.74, mean duplicate_p 0.01
- sweep: 5 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.42, mean duplicate_p 0.01
- vista-dw-review: 2 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.21, mean duplicate_p 0.01
```

The tracer bullet on PR 1110 alone (5 findings, 6 calls, $0.0004) gave the same shape: no label crossed 0.85, Jev rated 2 of 4 findings a level above the reviewer, and the one finding the skeptic called a pre-existing pattern (F1, the throwable in the ERROR line, cited lines written entirely in the PR) came back `introduced_by_this_diff` 0.68.

### How to read the numbers

- **Truth proxies, not labels.** `duplicate` truth is "the round-two title names a round-one finding number, or matches a round-one title at ratio 0.6 or more". That is the dw-review record's own "Finding 1 (...) has no pinning test" convention, so it marks follow-ons about the same subject, not only verbatim restatements. `introduced` truth is the skeptic's note when it says the defect predates the change (one row), else blame: at least half the cited lines written inside the PR. Blame is part of the state Jev receives, so the 0.93 precision mostly measures whether Jev reads `blame.written_in_this_change`.
- **PR 1063 round two has no rows.** The Multi-Agent Review found nothing, which is the loop's natural stop; the grader is only asked about findings, so this case contributes no convergence number. A live step would need the round question asked on an empty round too.
- **Severity.** Jev rated 31 of 46 findings higher than the reviewer and agreed with neither of the two skeptic demotions. On its own this says Jev is a stricter grader than these lanes, not that either is right; a `severity` question fed the skeptic's reasoning would be the next experiment.
- **PR 1065 round two.** 7 of its 25 findings grade as new HIGH or worse under Jev's severity (reviewer: 2 HIGH), and `round_materially_same_as_previous` came back 0.10. Either rule alone would have kept the loop open, which matches what happened (close-out PR 1110).
- **Cost.** 56 calls, 135,793 input tokens, $0.0057 for the whole corpus; a per-round shadow step on a 25-finding review costs about 27 calls and half a cent.

## Validate next

1. Shadow step inside `dw-review` / `vista-dw-review` / `zord-multi-agent-review` that writes the six answers per round to `~/.local/state/jevdev/triage.jsonl` and changes nothing; log-only duplicate threshold 0.5.
2. Keep finding-fixer's Step 5 lines somewhere durable (the saved review record is the natural place) so `fixer` rulings join the corpus; `fix_is_mechanical` has no truth signal until then.
3. Re-run `corpus_findings.py --limit 15` after five more multi-round loops land and recut with `calibrate_findings.py --from-graded` plus one live run.
