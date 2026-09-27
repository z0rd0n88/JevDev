# Jev feature opportunities

**Date:** 2026-09-27

**Status:** Ideas for evaluation; none of these features is implemented or validated.

## Design boundary

Jev is useful here for a small semantic judgment over a short, relevant piece of text. Its [Choice and Noul answers](https://docs.typesafe.ai/primitives) can inform a decision, while ordinary code retains exact checks on paths, counts, Git state, permissions, and timestamps. The [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) argue against using it for arithmetic, long chains of inference, or an authorization decision by itself.

These ideas extend the standalone Claude/Codex skill router. They do not imply that either host already has a Jev integration.

## 1. Scope Sentinel

Before a consequential agent action, compare a compact record of the latest user instruction, active constraints, and proposed action. Jev would judge whether the action is explicitly covered, ambiguous, or in conflict with the stated scope. The host's existing permission checks and deterministic rules would still decide what can run; Jev could only flag the action for review.

Examples include a proposed push after a review-only request, a deployment after a request to prepare deployment materials, or an action that has drifted from the named target set. This differs from the cookbook's [general LLM guardrails](https://docs.typesafe.ai/cookbooks/llm_guardrails): it follows the user's changing authorization across an agent task.

**First test:** Build blind-labeled instruction–action pairs from consented or authored examples. Run the classifier in shadow mode, then compare missed scope violations and unnecessary interruptions with a deterministic rule-only baseline. Do not select a live blocking threshold until the held-out results are reviewed.

**Main risk:** A semantic classifier can misunderstand negation, later corrections, or adversarial text. It must never grant permission on its own.

## 2. Decision Drift Radar

Pair one recorded owner decision with one relevant PR change summary or diff hunk. Jev would classify whether the change appears to implement, contradict, or leave the decision unaddressed, and whether it fills in a value the owner explicitly deferred. Code would retrieve the relevant pair and preserve links to the source decision and exact diff.

**First test:** Have a reviewer label a small set of decision–change pairs before inspecting Jev's answers. Measure contradicted decisions found and false alerts. Treat every flag as a review lead, not proof about code behavior.

**Main risk:** A short diff hunk can omit the context needed to understand an implementation. An `unclear` outcome should stay visible.

## 3. Handoff Integrity Check

Compare each item in a compact decision ledger with the next task handoff. Jev would flag a missing constraint, an unfinished item described as complete, or a changed next step. Code would keep the original text and source location beside each flag.

**First test:** Create handoffs with known omissions and harmless paraphrases. Measure whether the check catches the former without treating the latter as errors.

**Main risk:** Long handoffs invite irrelevant context and multi-step inference. Compare one ledger item with one handoff passage at a time.

## 4. Benchmark Fixture Curator

Before a prompt enters the skill-router benchmark, use Jev to flag whether it is self-contained and whether more than one skill label is defensible. Deterministic checks would handle duplicate prompts, missing fields, and fixture format. A human would settle ambiguous labels before any model observations are examined.

**First test:** Run the curator against authored pilot prompts, with separate human review of flagged and unflagged samples. Measure label disagreements and missed ambiguity. This improves the evidence used to evaluate routing; it does not establish router accuracy.

**Main risk:** A curator that shares the router's biases can make the benchmark look cleaner without making it more representative.

## Recommendation

Start with **Scope Sentinel** as a standalone, shadow-mode experiment because it addresses a costly failure in agent workflows without requiring immediate host installation. Benchmark Fixture Curator is the smallest addition to the existing JevDev pilot. Use action-specific thresholds only after observing false permits and false interruptions; [confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing) provides a pattern, not a universal threshold.

The [TypeSafe cookbooks](https://docs.typesafe.ai/cookbooks) already cover skill suggestion, generic guardrails, and citation checking; [intent routing](https://docs.typesafe.ai/patterns/intent-routing) is a documented pattern. These proposals target task continuity and reviewable agent actions.
