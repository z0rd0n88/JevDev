# Idea Nebula: Jev applications beyond skill routing

**Date:** 2026-09-27

**Status:** Research and product hypotheses; no idea below has a validated Jev accuracy claim or proven market demand.

## Method and result

Four independent idea-generation approaches produced 18 concepts. An LLM ranker compared eight of them in both presentation orders without seeing which approach generated each idea. Ten other concepts were set aside to keep the comparison manageable; they were **not** shown to be inferior on every dimension. A timeboxed live-source scan checked five finalists for independent complaints and paid substitutes. The pairwise standings are subjective ideation judgments, not an experiment with users.

For every concept, Jev would answer a narrow [Choice, Score, or Noul question](https://docs.typesafe.ai/primitives). Parsers, hashes, test results, environment changes, and permissions remain in code. [Jev 1.13's documented limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) make that split essential.

**Best fit for JevDev:** Contract Fracture Lab, a small matched-task comparison of Claude and Codex. **Smallest useful safety pilot:** Test Intent Escrow. Both need labeled results before any host integration.

## Safe picks

| Idea | Pairwise W-D-L | Jev's narrow job | Affordable first step | Main risk |
|---|---:|---|---|---|
| **Skill Bankruptcy Court** | 4-3-0 | Judge whether paired runs with and without one skill clause differ in the intended behavior | Two clauses across ten fixed tasks | Interacting clauses confound attribution; [Tessl](https://docs.tessl.io/support/faqs) and [Oqoqo](https://oqoqo.ai/pricing) already offer skill evaluation |
| **Cold Start Fuzzer** | 4-2-1 | Classify an ambiguous failure log after code removes one setup prerequisite in a disposable environment | Replay one JevDev workflow under four perturbations | The environment may fail for unrelated reasons; simpler setup checks may suffice |
| **Test Intent Escrow** | 4-1-2 | Judge whether an edited assertion still protects the previously stated behavior | Read-only report on changed tests and a human review | Legitimate requirement changes can look like weakening |
| **Review Exit Court** | 1-1-5 | Judge whether a new AI review finding adds relevant, material information to the original task | Compare two review rounds against a frozen task and diff | A late real defect could be dismissed |

Test Intent Escrow has concrete reports of agents weakening tests in [Claude Code](https://github.com/anthropics/claude-code/issues/7074) and [Codex](https://github.com/openai/codex/issues/24922). Its distinct contribution would be preserving **test intent**, beyond detecting that a test file changed. Existing broad [AI code review](https://www.coderabbit.ai/pricing) and deterministic test-change tools make false-positive reduction the critical question.

## Moonshots

These are high-variance bets retained for their distance from the generic guardrail/review cluster. Most should be discarded if a small validation fails.

| Idea | Pairwise W-D-L | Jev's narrow job | Affordable first step | Main risk |
|---|---:|---|---|---|
| **Contract Fracture Lab** | 6-1-0 | Classify paired Claude/Codex trace excerpts as same action, omission, extra action, changed interpretation, or unclear | Five matched, read-only sandbox tasks with exact tool-call capture | Hidden host behavior can prevent a clean explanation |
| **Assumption Recall** | 2-2-3 | Judge whether a short artifact summary depends on a newly invalidated premise | A local premise-to-artifact graph with human-confirmed links | An incomplete graph misses affected work |
| **Screen-Reader Diff Route** | 1-2-4 | Rank diff hunks against a maintainer's bug report while preserving access to every hunk | A keyboard-friendly Markdown view of one local diff | A consequential hunk could be ranked low; actual screen-reader users must validate it |
| **Work Product Quarantine** | 0-0-7 | Judge whether an artifact depends on a failed or interrupted step | Analyze one interrupted local run with exact hashes and statuses | A missed dependency makes stale work look reusable |

A [Claude/Codex skill-discovery difference](https://github.com/anthropics/claude-code/issues/20979) motivates the Contract Fracture Lab, but a static migration audit does not prove demand for matched execution traces. A [stale-plan report](https://github.com/anthropics/claude-code/issues/27319) motivates Assumption Recall, but the persistent graph is the difficult part.

## Demand evidence

The scan counted distinct relevant authors or threads, not posts or market prevalence. Its 20-complaint cutoff is a screening rule from the Idea Nebula workflow, not a measure of usefulness to JevDev. All five checks fell short for the **specific proposed solution**. Paid substitutes exist, but no reviewed source showed a paid vendor failing at exactly these jobs; the workflow's vendor-gap multiplier is therefore zero for all five.

| Idea | Timeboxed complaint count | Strongest directly linked example | Paid adjacent substitute | Screening result |
|---|---:|---|---|---|
| Contract Fracture Lab | 11 adjacent portability reports; few about matched traces | [Codex recognizes a skill that Claude misses](https://github.com/anthropics/claude-code/issues/20979) | [Bring Your AI](https://bringyour.ai/) migration tooling | Demand unproven |
| Skill Bankruptcy Court | 21 broad skill complaints; no direct request for measured clause retirement | [Skills read but not reliably followed](https://github.com/openai/codex/issues/34189) | [Tessl](https://docs.tessl.io/support/faqs), [Oqoqo](https://oqoqo.ai/pricing) | Crowded; deprioritize |
| Cold Start Fuzzer | 12 adjacent setup failures | [Valid skills reported as missing](https://github.com/anthropics/claude-code/issues/20576) | [Agent sandboxes](https://e2b.dev/pricing) | Demand unproven |
| Test Intent Escrow | 17 relatively direct test-manipulation reports | [Assertion weakening report](https://github.com/anthropics/claude-code/issues/7074) | [AI code review](https://www.coderabbit.ai/pricing) | Closest demand signal; still below cutoff |
| Assumption Recall | 9 stale-premise reports | [Old plan revived after compaction](https://github.com/anthropics/claude-code/issues/27319) | [Requirements impact analysis](https://support.jamasoftware.com/hc/en-us/articles/40781365974541-Using-Trace-View-Coverage-Explorer-Impact-Analysis-in-Jama-Connect) | Demand unproven |

These links support the existence of reported failures. They do **not** establish how often the failures occur, classifier accuracy, or willingness to pay for a new tool.

## Other viable concepts not in the eight-way comparison

These were excluded by an editorial focus on founder fit and a distinct Jev judgment, not by proof of inferiority. Demand was not checked individually.

| Concept | Specific Jev role |
|---|---|
| **Progress Fuse** | Decide whether differently worded agent attempts repeat the same failed approach while code checks actual progress; a [Codex loop report](https://github.com/openai/codex/issues/37304) shows the pain |
| **CSV Dialect Memory** | Suggest or abstain on mapping changed supplier CSV headers to known fields; a user approves after type and row previews |
| **Freshness Receipts** | Classify how quickly a factual claim is likely to become stale so code can schedule re-verification |
| **Explain This Change** | Find a diff hunk a student cannot clearly connect to their own explanation, prompting a walkthrough without making an authorship accusation |
| **Parallelism Taximeter** | Judge whether two agent summaries represent independent progress while code measures overlap and cost |
| **Completion Receipt** | Relate a completion claim to recorded commands and probes; code preserves exact commit and exit-status evidence |
| **Verification Queue** | Relate a model, tool, or dependency update to saved validation claims that may need rerunning |
| **Shift Story to Replay** | Rank log windows against a frontline user's failure description so a human can specify expected behavior for a regression fixture |
| **Failure Cause Map** | Classify ambiguous failure prose as tool, permission, environment, model, or reasoning trouble after exact statuses are parsed |
| **Demo Path Shortlist** | Map a non-engineer's product promise to likely UI routes and controls; code checks whether the path still opens |

## Modal region and disagreement

Generic guardrails, routing, review, and freshness warnings are the crowded center. Several concepts converge on rechecking earlier work; Test Intent Escrow is narrower because it asks whether an edited test still means the same thing. The blind ranking favored Skill Bankruptcy Court, but the demand check found direct overlap with existing paid evaluators. Contract Fracture Lab won the most pairwise comparisons yet has only adjacent portability complaints, so its originality should be tested through a small replay rather than assumed to be a product advantage.

## Validate next

1. **Test Intent Escrow:** Blind-label 30 changed-test examples. Compare a deterministic diff-only baseline with diff plus Jev on missed weakening and needless flags. Keep all outputs advisory.
2. **Contract Fracture Lab:** Run five matched, read-only tasks in Claude and Codex. Pin host versions, task inputs, and tool traces; manually label differences before inspecting Jev's classifications. If exact trace comparison explains every difference, Jev adds no value.

This ranking is a funnel, not a verdict. A [randomized execution study](https://arxiv.org/abs/2506.20803) found that ideas judged novel before implementation did not retain that advantage after researchers built them. JevDev should use the pilots, not pairwise standings, to decide what to build.
