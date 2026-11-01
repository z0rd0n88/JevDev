# Finding Triage and Convergence, phase 1: corpus and offline calibration

**Date:** 2026-10-31, regraded 2026-11-01 after the second PR #58 review. **Scope:** the 15 most recently merged PRs of `VistaMarkets/VistaMobileBE` (#1054 to #1111), their PR comments, the review records saved in that checkout, and the Claude and Codex transcripts that name them. **Status:** offline only. No review skill, hook, or setting was changed. Thresholds are provisional and live in `finding_triage.py`.

Idea and demand evidence: [`docs/ideas/jev-features-nebula.md`](../ideas/jev-features-nebula.md), Run 3, Safe Pick 1.

## Verdict on the 0.85 thresholds

**Not safe to move into a shadow step, and the corpus cannot yet say whether any threshold would be.** The 0.85 duplicate threshold never fires. Rewording the question moved the scores more than any threshold does: with the 25 round-two findings of the one multi-round loop hand-labelled, the two true duplicates (F13, F17) went from 0.23 and 0.28 to 0.61 and 0.50 once the question said "same defect, at the same or additional sites" and named a missing test as not a duplicate, and the "no pinning test" rows fell (F4 0.52 to 0.15, F5 0.54 to 0.24). At 0.5 it now catches both duplicates with 4 false positives (precision 0.33, recall 1.00): F1 and F12, defects the prior fix created, and refuted rows F22 and F24. That is a better question, not a calibrated one: there are two positives, and the wording was written with these labels and earlier scores in hand, so nothing here is held out. `introduced_by_this_diff` at the effective threshold (p over 0.15) matches an always-introduced baseline exactly (precision 0.95, recall 1.00 for both): on a feature PR almost every cited line is new, so the question has nothing to discriminate here. The convergence rule kept PR 1065's loop open, which matches the close-out PR that followed, but one loop is not evidence either way. The next phase needs data where the questions can fail, loops whose re-review restates findings and PRs that touch old code, and the question should be tested on rows it was not written against.

## What was built

| File | What it does |
|---|---|
| `finding_triage.py` | Parses the four report shapes the review skills post, builds per-finding state (finding, cited hunk ±15 lines, blame age and share written in the PR, prior-round findings), asks Jev the four per-finding questions plus the per-round `round_materially_same_as_previous` and `keystone` questions through `jev_patterns.call`, labels, and decides convergence. Hunks are redacted before they reach Jev. A finding with no readable hunk or blame is graded but never labelled pre-existing, and the reason is recorded on the row. Refuted findings never count as new HIGH. |
| `corpus_findings.py` | Builds `.local/findings-corpus.jsonl`: one row per (PR, round, finding) from PR comments, `docs/reviews` and `.claude/reviews` in the checkout, and Claude + Codex transcripts; orders reports into rounds, merges copies of the same report, joins finding-fixer rulings. The PR set is fetched live; per-PR detail and comments are cached under `.local/raw` (owner-only; decoded before redacting so the JSON stays valid, a file that no longer parses is refetched; `--refresh` refetches). |
| `calibrate_findings.py` | Replays the corpus through the grader and prints the numbers below; `--from-graded` re-cuts the report without new Jev calls. Rows go to a `.tmp` file that replaces the output only when every round is graded, and a `--pr` run writes beside the full file. Truth comes from hand labels where a round has them, else from a title proxy, and the two are compared. |
| `tests/fixtures/findings/labels-pr1065-r2.json` | Hand labels for the 25 round-two findings of PR 1065: duplicate, follow_on, the prior-round id, one-line reason. Ids and booleans only. |
| `tests/test_finding_triage.py` | Seventeen offline checks with a stub `jev`: the parser on three real redacted review texts, the Multi-Agent Review bucket format with en-dash ranges, finding-fixer report lines, redaction (secret shapes, JSON forms and round-trips, code and constants left alone, speed on a keyword run), the JSON cache, bare-path resolution and blame against a throwaway git repo, a failed grade leaving the previous file intact, the `--pr` output path, grading on a 5-finding fixture, convergence over 2 rounds including a refuted HIGH. |

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

Run: `bash with_jev_key.sh python3 calibrate_findings.py` after the second review's fixes (widened duplicate question, JSON cache decoded before redacting, hunks redacted, temp-and-rename). The corpus rebuild before it was unchanged field for field from the previous build. Output, verbatim:

```
Rows: 51 findings in 4 rounds across 3 PRs. Live run; graded rows written to /home/alex/JevDev/.worktrees/finding-triage/.local/calibration.jsonl.

- duplicate_of_prior_round at 0.85 (rows with a prior round; 25 of 25 hand-labelled, the rest by title proxy): n=25 tp=0 fp=0 fn=2 tn=23 precision=n/a recall=0.00
  - at 0.3: n=25 tp=2 fp=15 fn=0 tn=8 precision=0.12 recall=1.00
  - at 0.4: n=25 tp=2 fp=13 fn=0 tn=10 precision=0.13 recall=1.00
  - at 0.5: n=25 tp=2 fp=4 fn=0 tn=19 precision=0.33 recall=1.00
  - at 0.6: n=25 tp=1 fp=3 fn=1 tn=20 precision=0.25 recall=0.50
  - at 0.7: n=25 tp=0 fp=2 fn=2 tn=21 precision=0.00 recall=0.00
  - title proxy vs hand label on the labelled rows: n=25 tp=0 fp=0 fn=2 tn=23 precision=n/a recall=0.00
  - mean duplicate_p on hand-labelled duplicate rows: 0.55 (n=2, min 0.50, max 0.61)
  - mean duplicate_p on hand-labelled follow_on rows: 0.35 (n=18, min 0.05, max 0.75)
  - mean duplicate_p on hand-labelled neither rows: 0.44 (n=5, min 0.06, max 0.63)
  - duplicate_p per row (truth in brackets: D duplicate, F follow-on, - neither): F1=0.75[F], F2=0.24[F], F3=0.42[F], F4=0.15[F], F5=0.24[F], F6=0.46[F], F7=0.27[F], F8=0.42[F], F9=0.18[F], F10=0.05[F], F11=0.11[F], F12=0.73[F], F13=0.61[D], F14=0.49[F], F15=0.42[F], F16=0.46[-], F17=0.50[D], F18=0.30[F], F19=0.45[F], F20=0.30[F], F21=0.41[F], F22=0.56[-], F23=0.48[-], F24=0.63[-], F25=0.06[-]
- introduced_by_this_diff at p > 0.15 (truth = blame, rows with readable blame only): n=42 tp=40 fp=2 fn=0 tn=0 precision=0.95 recall=1.00
  - always-introduced baseline on the same rows: n=42 tp=40 fp=2 fn=0 tn=0 precision=0.95 recall=1.00
  - at p > 0.3: n=42 tp=38 fp=1 fn=2 tn=1 precision=0.97 recall=0.95
  - at p > 0.5: n=42 tp=27 fp=0 fn=13 tn=2 precision=1.00 recall=0.68
  - at p > 0.7: n=42 tp=19 fp=0 fn=21 tn=2 precision=1.00 recall=0.47
  - excluded 9 rows: 7 no location cited; 2 WithdrawalRoutesTest.kt is absent or ambiguous at 391da5d7
  - vs the skeptic's 'pre-existing pattern' notes alone (truth false): n=1 tp=0 fp=1 fn=0 tn=0 precision=0.00 recall=n/a
- severity agrees with the reviewer's stated severity: 14/46; Jev higher: 31, lower: 1
  - raw severity score by stated level (0 LOW .. 3 CRITICAL): LOW n=17 mean 1.07 min 0.25 max 2.49; MEDIUM n=20 mean 1.75 min 1.22 max 2.62; HIGH n=8 mean 2.44 min 1.25 max 2.98; CRITICAL n=1 mean 2.84 min 2.84 max 2.84
  - agrees with the skeptic's demoted severity: 0/2
- REFUTED findings graded: 5; of them labelled duplicate 0, pre-existing 0, mechanical 0; they never count as new HIGH
- rows with a finding-fixer ruling: 0; mechanical label vs ruling fix-here: n=0 tp=0 fp=0 fn=0 tn=0 precision=n/a recall=n/a
- noted_not_blocking: 0, mechanical: 1, duplicate: 0, pre_existing: 0
- Jev calls: 56, input tokens: 138702, estimated cost: $0.0058

## Convergence

- PR 1063: 1 round(s); r1 n=2 new_high=0 same_p=None converged=False keystone=L2
- PR 1065: 2 round(s); r1 n=19 new_high=17 same_p=None converged=False keystone=MINT-1; r2 n=25 new_high=6 same_p=0.12 converged=False keystone=F1
- PR 1110: 1 round(s); r1 n=5 new_high=2 same_p=None converged=False keystone=F2

PRs with 2+ rounds: 1; would have stopped one round earlier under the provisional thresholds: 0.

## Per tool

- dw-review: 25 findings; duplicate 0, pre_existing 0, mechanical 1, mean introduced_p 0.46, mean duplicate_p 0.39, no blame 6
- multi-agent-review: 19 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.73, mean duplicate_p 0.01, no blame 0
- sweep: 5 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.44, mean duplicate_p 0.02, no blame 1
- vista-dw-review: 2 findings; duplicate 0, pre_existing 0, mechanical 0, mean introduced_p 0.21, mean duplicate_p 0.01, no blame 2
```

### How to read the numbers

- **Duplicate.** The hand labels and the Jev question now share one definition: same defect as a prior-round finding, at the same or additional sites. It was widened because the labels already counted F13 (cancellation still swallowed at sites the FAIL-4 fix missed) and F17 (`getGenesisHash` still unbounded after the CRYPTO-1 fix), both of which cite different lines from their priors, while the old question asked for the same place. The false criterion now names a defect the fix created and a missing test for the fix. Compared with the previous run, F13 went 0.23 to 0.61 and F17 0.28 to 0.50, and duplicates now score above follow-ons on average (0.55 against 0.35). The errors that remain have a pattern: F1 (0.75) and F12 (0.73) are defects the fix created, and the refuted rows F22, F23, F24 (0.56, 0.48, 0.63) have no location and a title about a same-round finding. Among unrefuted rows at 0.5 there are two true and two false positives. The title proxy (ratio 0.6) finds neither duplicate; it was never a usable stand-in, and the earlier "precision 0.75 at 0.5" stays withdrawn.
- **Run-to-run movement.** The three questions whose wording did not change also moved between the two runs, by a mean absolute 0.038 for `introduced_by_this_diff` (max 0.16), 0.039 for the severity score (max 0.18), and 0.019 for `fix_is_mechanical` (max 0.10). On the round-two rows `duplicate_of_prior_round` moved by 0.177 (max 0.38), so the rewording effect is well above that background. Small moves still flip counts when scores cluster near a cut: `introduced` at p over 0.5 went from 33 to 27 true positives with its question unchanged, and F17 now sits on 0.50 exactly. All four questions share one call, so two runs cannot separate sampling from the effect of the changed wording.
- **Introduced.** Truth is blame alone (at least half the cited lines written inside the PR). On a feature PR that is true of 40 of the 42 rows with readable blame, so the always-introduced baseline scores the same as Jev and the question is untestable here; the probabilities do spread (19 rows over 0.7, 2 true negatives found at 0.5 and above), which is all that can be said. The skeptic's one "repeat of an existing pattern" note (PR 1110 F1) is about a pattern elsewhere, not the cited lines, and is reported on its own line rather than mixed into truth.
- **Severity.** Jev's raw score rises with the stated level (LOW 1.07, MEDIUM 1.75, HIGH 2.44, CRITICAL 2.84 on a 0 to 3 scale) but is compressed toward the middle: LOW sits a full level above its index, MEDIUM 0.75 above, HIGH 0.44 above, CRITICAL 0.16 below. Rounding then lifts most LOW and MEDIUM findings one level while HIGH and CRITICAL mostly hold. Whether that is Jev grading the low end harder or the scale reading differently from the rubric cannot be settled from these rows; the raw score is stored so a different cut can be tried without new calls.
- **Labels.** The 25 hand labels were written by one annotator, the author of this report, in one pass from the dw-review record and the Multi-Agent Review report, after seeing the first run's scores. They were rechecked against the wider definition before this regrade and none changed. The closest call is F19 (Exposed index parity still short after SCHEMA-5), labelled a follow-on and scored 0.45; counting it as a duplicate would drop recall at 0.5 to 2 of 3. A second annotator would be the cheapest check on all of this.
- **Convergence.** PR 1065 round two has 6 new HIGH or worse by Jev's severity after excluding the 4 refuted rows, and `round_materially_same_as_previous` came back 0.12. Either rule alone keeps the loop open, which matches what happened (close-out PR 1110). PR 1063's second round found nothing, which is the loop's natural stop; the calibration harness groups rows per finding and so never asks the round question of an empty round.
- **Cost.** 56 calls, 138,702 input tokens, $0.0058 for the whole corpus; a per-round shadow step on a 25-finding review costs about 27 calls and half a cent.

## Validate next

1. Build the corpus from the saved review records (`docs/reviews`, `.claude/reviews` across the repo's history) rather than from merged PRs, so the multi-round loops the idea targets are in the sample; hand-label every round-two set the same way as `labels-pr1065-r2.json`.
2. Test the widened `duplicate_of_prior_round` on the new loops before changing it again. If defects a fix created keep scoring high (F1, F12), add the prior finding's failure path to the state, which the per-finding, round and keystone questions all lack, or split out a separate "created by the prior fix" question. Grade the same rows at least twice to measure run-to-run movement.
3. Keep finding-fixer's Step 5 lines somewhere durable (the saved review record is the natural place) so `fixer` rulings join the corpus; `fix_is_mechanical` has no truth signal until then.
4. Re-run `corpus_findings.py --refresh` with the same pinned `--pr` list plus the new loops, regrade once live, and re-cut with `calibrate_findings.py --from-graded` for any further analysis.
