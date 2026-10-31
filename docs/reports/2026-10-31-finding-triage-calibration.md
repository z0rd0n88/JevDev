# Finding Triage and Convergence, phase 1: corpus and offline calibration

**Date:** 2026-10-31 (regraded the same day after the PR #58 review). **Scope:** the 15 most recently merged PRs of `VistaMarkets/VistaMobileBE` (#1054 to #1111), their PR comments, the review records saved in that checkout, and the Claude and Codex transcripts that name them. **Status:** offline only. No review skill, hook, or setting was changed. Thresholds are provisional and live in `finding_triage.py`.

Idea and demand evidence: [`docs/ideas/jev-features-nebula.md`](../ideas/jev-features-nebula.md), Run 3, Safe Pick 1.

## Verdict on the 0.85 thresholds

**Not safe to move into a shadow step, and the corpus cannot yet say whether any threshold would be.** With the 25 round-two findings of the one multi-round loop hand-labelled, only two are duplicates in the sense the Jev question asks (same defect, same place: F13 and F17). Jev scored those two at 0.23 and 0.28, below every threshold from 0.3 up, while the eighteen follow-on findings (a new defect about a prior subject, mostly "fix landed, no pinning test") averaged 0.40. So `duplicate_of_prior_round` separates nothing on this corpus; the earlier "0.5 gives precision 0.75" number was the title proxy counting follow-ons as duplicates, and it is withdrawn. `introduced_by_this_diff` at the effective threshold (p over 0.15) matches an always-introduced baseline exactly (precision 0.95, recall 1.00 for both): on a feature PR almost every cited line is new, so the question has nothing to discriminate here. The convergence rule kept PR 1065's loop open, which matches the close-out PR that followed, but one loop is not evidence either way. What the next phase needs is not a different threshold but data where the questions can fail: loops whose re-review restates findings, and PRs that touch old code. Until then a shadow step would log only tautologies.

## What was built

| File | What it does |
|---|---|
| `finding_triage.py` | Parses the four report shapes the review skills post, builds per-finding state (finding, cited hunk ±15 lines, blame age and share written in the PR, prior-round findings), asks Jev the four per-finding questions plus the per-round `round_materially_same_as_previous` and `keystone` questions through `jev_patterns.call`, labels, and decides convergence. A finding with no readable hunk or blame is graded but never labelled pre-existing, and the reason is recorded on the row. Refuted findings never count as new HIGH. |
| `corpus_findings.py` | Builds `.local/findings-corpus.jsonl`: one row per (PR, round, finding) from PR comments, `docs/reviews` and `.claude/reviews` in the checkout, and Claude + Codex transcripts; orders reports into rounds, merges copies of the same report, joins finding-fixer rulings. The PR set is fetched live; per-PR detail and comments are cached under `.local/raw` (owner-only, redacted; `--refresh` refetches). |
| `calibrate_findings.py` | Replays the corpus through the grader and prints the numbers below; `--from-graded` re-cuts the report without new Jev calls. Truth comes from hand labels where a round has them, else from a title proxy, and the two are compared. |
| `tests/fixtures/findings/labels-pr1065-r2.json` | Hand labels for the 25 round-two findings of PR 1065: duplicate, follow_on, the prior-round id, one-line reason. Ids and booleans only. |
| `tests/test_finding_triage.py` | Nine offline checks with a stub `jev`: the parser on three real redacted review texts, the Multi-Agent Review bucket format with en-dash ranges, finding-fixer report lines, redaction of eleven secret shapes with JSON round-trip, bare-path resolution and blame against a throwaway git repo, grading on a 5-finding fixture, convergence over 2 rounds including a refuted HIGH. |

## Corpus

Build: `python3 corpus_findings.py --refresh --pr 1111 --pr 1110 ... --pr 1054` (the PR set pinned so the regrade covers the same PRs as the first run). Output, verbatim:

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

State the grader could not build: 7 findings cite no location (the two PR 1063 docs findings, PR 1110's refuted F5, PR 1065's four refuted rows), and 2 cite `WithdrawalRoutesTest.kt`, which exists twice at the reviewed commit. Those 9 rows were graded from text alone and are excluded from the blame-based numbers below; the first graded run (before the PR #58 review) had sent an empty hunk and a zero-line blame for the two ambiguous rows and called one of them pre-existing.

## Calibration

Run: `bash with_jev_key.sh python3 calibrate_findings.py` after the review fixes (en-dash line ranges, ambiguous-path handling, redaction, cache refresh, hand labels). Output, verbatim:

```
Rows: 51 findings in 4 rounds across 3 PRs. Live run; graded rows written to .local/calibration.jsonl.

- duplicate_of_prior_round at 0.85 (rows with a prior round; 25 of 25 hand-labelled, the rest by title proxy): n=25 tp=0 fp=0 fn=2 tn=23 precision=n/a recall=0.00
  - at 0.3: n=25 tp=0 fp=17 fn=2 tn=6 precision=0.00 recall=0.00
  - at 0.4: n=25 tp=0 fp=9 fn=2 tn=14 precision=0.00 recall=0.00
  - at 0.5: n=25 tp=0 fp=8 fn=2 tn=15 precision=0.00 recall=0.00
  - at 0.6: n=25 tp=0 fp=3 fn=2 tn=20 precision=0.00 recall=0.00
  - at 0.7: n=25 tp=0 fp=1 fn=2 tn=22 precision=0.00 recall=0.00
  - title proxy vs hand label on the labelled rows: n=25 tp=0 fp=0 fn=2 tn=23 precision=n/a recall=0.00
  - mean duplicate_p on hand-labelled duplicate rows: 0.26 (n=2, min 0.23, max 0.28)
  - mean duplicate_p on hand-labelled follow_on rows: 0.40 (n=18, min 0.03, max 0.77)
  - mean duplicate_p on hand-labelled neither rows: 0.25 (n=5, min 0.03, max 0.33)
  - duplicate_p per row (truth in brackets: D duplicate, F follow-on, - neither): F1=0.61[F], F2=0.16[F], F3=0.37[F], F4=0.52[F], F5=0.54[F], F6=0.51[F], F7=0.50[F], F8=0.77[F], F9=0.33[F], F10=0.03[F], F11=0.08[F], F12=0.41[F], F13=0.23[D], F14=0.35[F], F15=0.14[F], F16=0.32[-], F17=0.28[D], F18=0.30[F], F19=0.60[F], F20=0.38[F], F21=0.56[F], F22=0.33[-], F23=0.26[-], F24=0.32[-], F25=0.03[-]
- introduced_by_this_diff at p > 0.15 (truth = blame, rows with readable blame only): n=42 tp=40 fp=2 fn=0 tn=0 precision=0.95 recall=1.00
  - always-introduced baseline on the same rows: n=42 tp=40 fp=2 fn=0 tn=0 precision=0.95 recall=1.00
  - at p > 0.3: n=42 tp=39 fp=1 fn=1 tn=1 precision=0.97 recall=0.97
  - at p > 0.5: n=42 tp=33 fp=0 fn=7 tn=2 precision=1.00 recall=0.82
  - at p > 0.7: n=42 tp=14 fp=0 fn=26 tn=2 precision=1.00 recall=0.35
  - excluded 9 rows: 7 no location cited; 2 WithdrawalRoutesTest.kt is absent or ambiguous at 391da5d7
  - vs the skeptic's 'pre-existing pattern' notes alone (truth false): n=1 tp=0 fp=1 fn=0 tn=0 precision=0.00 recall=n/a
- severity agrees with the reviewer's stated severity: 14/46; Jev higher: 31, lower: 1
  - raw severity score by stated level (0 LOW .. 3 CRITICAL): LOW n=17 mean 1.07 min 0.23 max 2.34; MEDIUM n=20 mean 1.73 min 1.22 max 2.54; HIGH n=8 mean 2.44 min 1.29 max 2.98; CRITICAL n=1 mean 2.79 min 2.79 max 2.79
  - agrees with the skeptic's demoted severity: 0/2
- REFUTED findings graded: 5; of them labelled duplicate 0, pre-existing 0, mechanical 0; they never count as new HIGH
- rows with a finding-fixer ruling: 0; mechanical label vs ruling fix-here: n=0 tp=0 fp=0 fn=0 tn=0 precision=n/a recall=n/a
- noted_not_blocking: 0, mechanical: 1, duplicate: 0, pre_existing: 0
- Jev calls: 56, input tokens: 137361, estimated cost: $0.0058

## Convergence

- PR 1063: 1 round(s); r1 n=2 new_high=0 same_p=None converged=False keystone=L2
- PR 1065: 2 round(s); r1 n=19 new_high=16 same_p=None converged=False keystone=MINT-1; r2 n=25 new_high=6 same_p=0.11 converged=False keystone=F1
- PR 1110: 1 round(s); r1 n=5 new_high=2 same_p=None converged=False keystone=F2

PRs with 2+ rounds: 1; would have stopped one round earlier under the provisional thresholds: 0.

## Per tool

- dw-review: 25 findings; duplicate 0, pre_existing 0, mechanical 1, mean introduced_p 0.47, mean duplicate_p 0.36, no blame 6
- multi-agent-review: 19 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.73, mean duplicate_p 0.01, no blame 0
- sweep: 5 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.43, mean duplicate_p 0.01, no blame 1
- vista-dw-review: 2 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.20, mean duplicate_p 0.01, no blame 2
```

### How to read the numbers

- **Duplicate.** The hand labels and the Jev question agree on the definition (same defect, same place, however reworded). Only F13 (cancellation still swallowed at eight sites the FAIL-4 fix missed) and F17 (`getGenesisHash` still unbounded after the CRYPTO-1 fix) qualify; Jev put both below 0.3. Follow-ons score higher than duplicates, so whatever `duplicate_p` measures on this corpus, it is closer to "about a prior subject" than "the same defect". The title proxy (ratio 0.6) finds neither duplicate either; it was never a usable stand-in. The earlier run's "precision 0.75 at 0.5" came from the proxy counting "Finding N has no pinning test" rows as restatements and is withdrawn.
- **Introduced.** Truth is blame alone (at least half the cited lines written inside the PR). On a feature PR that is true of 40 of the 42 rows with readable blame, so the always-introduced baseline scores the same as Jev and the question is untestable here; the probabilities do spread (14 rows over 0.7, 2 true negatives found at 0.5 and above), which is all that can be said. The skeptic's one "repeat of an existing pattern" note (PR 1110 F1) is about a pattern elsewhere, not the cited lines, and is reported on its own line rather than mixed into truth.
- **Severity.** Jev's raw score rises with the stated level (LOW 1.07, MEDIUM 1.73, HIGH 2.44, CRITICAL 2.79 on a 0 to 3 scale) but sits roughly 0.7 above it at every level, and rounding then lands most findings one level higher than the reviewer. Whether that is Jev grading harder or the scale reading differently from the rubric cannot be settled from these rows; the raw score is now stored so a different cut can be tried without new calls.
- **Convergence.** PR 1065 round two has 6 new HIGH or worse by Jev's severity after excluding the 4 refuted rows (the first run counted one of them), and `round_materially_same_as_previous` came back 0.11. Either rule alone keeps the loop open, which matches what happened (close-out PR 1110). PR 1063's second round found nothing, which is the loop's natural stop; the calibration harness groups rows per finding and so never asks the round question of an empty round.
- **Cost.** 56 calls, 137,361 input tokens, $0.0058 for the whole corpus; a per-round shadow step on a 25-finding review costs about 27 calls and half a cent.

## Validate next

1. Build the corpus from the saved review records (`docs/reviews`, `.claude/reviews` across the repo's history) rather than from merged PRs, so the multi-round loops the idea targets are in the sample; hand-label every round-two set the same way as `labels-pr1065-r2.json`.
2. Rewrite `duplicate_of_prior_round` as two questions, "same defect" and "follow-on about a prior finding", since Jev's current answer tracks the second; or add the prior finding's failure path to the state, which the round and keystone questions also lack.
3. Keep finding-fixer's Step 5 lines somewhere durable (the saved review record is the natural place) so `fixer` rulings join the corpus; `fix_is_mechanical` has no truth signal until then.
4. Re-run `corpus_findings.py --refresh` with the same pinned `--pr` list plus the new loops, regrade once live, and re-cut with `calibrate_findings.py --from-graded` for any further analysis.
