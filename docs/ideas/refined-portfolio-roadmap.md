# JevDev Prototype Portfolio: Refinement & Strategic Roadmap

**Date:** 2026-10-12  
**Skill:** `/agent-skills:idea-refine`  
**Status:** Converged Strategy & Actionable One-Pagers  

---

## 1. Executive Summary & Convergence Roadmap

Across the 6 prototypes developed for Jev, the portfolio splits into two distinct categories: **Agent Safety & Boundary Enforcers** (high value, high urgency) and **Context/Data Preprocessors** (mixed value, one critical anti-pattern).

### Roadmap Clustering

| Tier | Prototype | Verdict | Core Rationale |
|---|---|---|---|
| **Tier 1 (Ship Next)** | **Test Intent Escrow** | **P0 Ship** | Direct, acute pain point (agents weakening tests to pass). High differentiation over static git hooks. Compact diff scope. |
| **Tier 1 (Ship Next)** | **Scope Sentinel** | **P0 Ship** | Working shadow-v2 hook, zero user latency (detached judge), prevents destructive actions (`push`, `rm -rf`, `pr merge`). |
| **Tier 2 (Promising / Validate)** | **Handoff Integrity Check** | **P1 Pilot** | Essential for multi-agent delegation & session compaction. Needs calibration on paraphrasing vs. omission. |
| **Tier 2 (Promising / Validate)** | **Decision Drift Radar** | **P1 Pilot** | High architectural value (ADR enforcement in PRs), but needs PR-level summary context rather than isolated raw diff hunks. |
| **Tier 2 (Internal Tooling)** | **Benchmark Fixture Curator** | **Maintain Internally** | Validates benchmark integrity; keep as internal CI check for JevDev evaluation fixtures, not a standalone product. |
| **Tier 3 (Kill / Not Doing)** | **Smart Reader** | **KILL** | **Anti-pattern.** Sequential 50-line chunk filtering via LLM is economically upside-down, adds 20-40s latency, and fragments code syntax. |

---

## 2. Phase 1: Understand & Expand (Divergent Thinking)

### Crisp "How Might We" Formulations

1. **Test Intent Escrow**: *How might we stop autonomous coding agents from quietly softening, skipping, or deleting test assertions to fabricate green test suites?*
2. **Scope Sentinel**: *How might we prevent coding agents from executing out-of-scope or destructive CLI actions without blocking developer velocity or introducing latency?*
3. **Handoff Integrity Check**: *How might we guarantee that hard architectural constraints and unfinished tasks survive multi-agent delegation and LLM context compaction?*
4. **Decision Drift Radar**: *How might we catch code changes that silently violate recorded architectural decisions before they merge into main?*
5. **Benchmark Fixture Curator**: *How might we ensure prompt benchmarks measure true router capability rather than ambiguous prompts or author bias?*
6. **Smart Reader**: *How might we feed only relevant code into an LLM context without paying full-file token costs?*

### Painkiller vs. Speculative Vitamin Triage

- **Acute Painkillers**:
  - **Test Intent Escrow**: Real, widespread user grievance across Claude Code and Codex. Agents asked to "fix tests" routinely rewrite the test to match broken code.
  - **Scope Sentinel**: Burning risk in autonomous agent runs. An agent asked to "audit branch" running `git push origin main` or deleting files is catastrophic.
- **High-Value Controls (Vitamins transitioning to Painkillers)**:
  - **Handoff Integrity Check**: Becomes an acute painkiller the moment teams adopt multi-agent swarms (e.g. MemPalace, Claude subagents) where tasks drift across hops.
  - **Decision Drift Radar**: Strong painkiller in teams with strict ADRs, but depends heavily on having well-maintained decision logs.
- **Internal Utility**:
  - **Benchmark Fixture Curator**: High internal utility for JevDev's scientific integrity, low customer-facing product value.
- **Speculative Vitamin / Negative Value**:
  - **Smart Reader**: Vitamin that creates worse illness. Sequential chunking costs more in Jev tokens and latency than modern LLM context windows (200k–2M tokens) consume directly.

### Strategic Combinations & Unifications

#### Unification A: "The Verification Gate" (Test Escrow + Decision Drift)
Instead of two isolated diff tools, unify them into a single git/PR verification gate:
- When a PR or commit occurs, the gate splits the diff into two buckets:
  1. `tests/**` files go to **Test Intent Escrow** (detect assertion weakening).
  2. `src/**` files go to **Decision Drift Radar** (detect contradiction against active ADRs / constraints).
- One command, unified report, complete code integrity coverage.

#### Unification B: "Task State Sentinel" (Scope Sentinel + Handoff Integrity)
- **Scope Sentinel** monitors *intra-session action execution* (prompt -> tool call).
- **Handoff Integrity** monitors *inter-session state transitions* (ledger -> handoff).
- Both evaluate compliance against the human's stated constraints using Jev's narrow choice classification.

#### Radical Pivot for Smart Reader: Kill Chunking, Adopt AST Symbol Ranking
If the goal is reducing context injection:
- Drop raw 50-line line chunking entirely.
- Use `ctags`/`tree-sitter` to parse file structure (classes, signatures), then use Jev to rank *which functions/methods* are relevant to the query.

---

## 3. Phase 2: Evaluate & Converge (Stress-Testing & Hidden Assumptions)

### Comparative Evaluation Matrix

| Prototype | User Value | Feasibility & Latency | Differentiation | Lethal Failure Mode |
|---|---|---|---|---|
| **Test Intent Escrow** | **Very High** (Stops agent cheating) | **High**: Diffs are compact; Jev `choice` is fast | High: Static linters only see syntax; generic review is bloated. Escrow is a focused gate. | Legitimate API changes that relax overly strict tests get flagged as violations, annoying devs. |
| **Scope Sentinel** | **Very High** (Blast-radius control) | **High**: Shadow mode is detached (0ms added); regex filters risky commands | High: Unlike static hooks, evaluates *intent* ("push to staging" vs "do not push"). | Prompt clipping misses earlier turns where user previously authorized the action. |
| **Handoff Integrity** | **High** (Multi-agent coordination) | **High**: Ledger items are short strings; batch query in 1 Jev request | High: Captures dropped constraints across handoff prose. | Paraphrased but faithful handoffs flagged as `changed` (false positive storm). |
| **Decision Drift Radar** | **Medium-High** (Architecture drift) | **Medium**: Single diff hunk lacks surrounding system context | Medium: Overlaps with LLM PR reviewers (CodeRabbit) unless anchored to exact ADR ledgers. | Diff hunk is too local; implementation is scattered across files, causing false `unaddressed` alerts. |
| **Benchmark Curator** | **Medium (Internal)** | **High**: Simple deterministic + noul checks | Low: Internal QA pipeline utility. | Curator shares model biases, artificially cleaning benchmarks to flatter the router. |
| **Smart Reader** | **Negative** (Wasteful overhead) | **Very Low**: N sequential calls = 30s+ latency, high token bill | None: Ripgrep, LSP, and 1M context windows render chunked LLM reading obsolete. | Fragmented chunks cut function bodies in half, corrupting syntax and context for the consumer. |

---

## 4. Phase 3: Sharpen & Ship — Detailed One-Pagers

### One-Pager 1: Test Intent Escrow

# Test Intent Escrow

## Problem Statement
How might we prevent autonomous coding agents from quietly weakening, skipping, or removing test assertions to make failing test suites pass?

## Recommended Direction
Build Test Intent Escrow as a focused pre-commit hook and PR review gate. 
Whenever an agent or developer touches files matching test patterns (`tests/**`, `*_test.py`), deterministic git diff tools extract the modified assertion lines and surrounding test bodies. Jev evaluates each test modification with a 3-way choice: `protects` (refactoring/preserving intent), `weakened` (softening boundaries or removing checks), or `unrelated` (setup/fixtures). 

Unlike heavy, multi-purpose AI code reviewers that comment on styling and trivia, Test Intent Escrow does exactly one job with zero latency on non-test files: it acts as an uncheatable escrow officer on test intent.

## Key Assumptions to Validate
- [ ] **Weakening Detectability**: Jev can reliably distinguish between semantic weakening (`assert x == 1` -> `assert x >= 0`) and valid test modernization (`assert x == 1` -> `assert res.value == 1`). *Test: Blind-label 30 real-world test diffs from agent sessions.*
- [ ] **Context Sufficiency**: The diff hunk and immediate enclosing test function provide enough context for Jev without needing the entire repository. *Test: Evaluate accuracy with hunk-only vs. full test function.*
- [ ] **Developer Tolerance**: False positive rate on legitimate test updates stays below 10%. *Test: Run across the last 50 human PRs in JevDev and measure false alarms.*

## MVP Scope
- **In**:
  - Deterministic test file filter (`tests/**`, `*test*.py`).
  - Git diff extractor isolating modified assertions.
  - CLI command: `test_escrow.py --diff <path>` and `test_escrow.py check-staged`.
  - Advisory exit codes (warn, do not hard-block until calibrated).
  - Jev Choice evaluation: `protects`, `weakened`, `unrelated`.
- **Out**:
  - Full codebase semantic analysis or AST execution.
  - Automatically rewriting or repairing the tests.
  - Inspecting non-test code files.

## Not Doing (and Why)
- **Not doing full PR code review**: Broad code review is crowded (CodeRabbit, GitHub Copilot) and high-noise. Test Intent Escrow remains surgical.
- **Not hard-blocking git commit on Day 1**: An uncalibrated hard block causes developer bypass (`--no-verify`). It runs advisory-first until false positive rates are proven.

## Open Questions
- How should Test Intent Escrow handle test deletions when a deprecated feature is intentionally removed alongside its tests?

---

### One-Pager 2: Scope Sentinel

# Scope Sentinel

## Problem Statement
How might we prevent coding agents from executing out-of-scope or destructive CLI commands without slowing down execution or interrupting the developer?

## Recommended Direction
Evolve Scope Sentinel (`shadow-v2`) into a calibrated, opt-in agent guardrail.
The architecture preserves its core breakthrough: a two-tier filter. Tier 1 is a fast, deterministic regex inside the host's `PreToolUse` hook (`RISKY` regex identifying `git push`, `commit`, `clean`, `gh pr merge`, `rm -rf`, `repo delete`). Safe commands (`git status`, `pytest`, `cargo build`) pass with 0.0ms overhead. 

For risky commands, Tier 2 redacts secrets, extracts the user's latest instruction and active constraints, and evaluates scope via Jev in detached shadow mode. Once calibrated on 100+ logged rows, Scope Sentinel can graduate from shadow logging to interactive user confirmation whenever an action is `conflict` or `ambiguous`.

## Key Assumptions to Validate
- [ ] **Instruction Freshness**: The latest user prompt in the transcript accurately reflects current intent, even in multi-turn conversations where authorization was granted 2 turns ago. *Test: Benchmark 50 multi-turn transcripts.*
- [ ] **Zero Latency Overhead**: The detached judge process never stalls or stutters the Claude/Codex execution thread. *Test: Verify sub-5ms hook execution in live agent sessions.*
- [ ] **Calibration Stability**: High confidence (>0.85) `conflict` verdicts correlate >95% with genuine human disapproval of the action. *Test: Audit `.local/sentinel.jsonl` logs against human engineer review.*

## MVP Scope
- **In**:
  - PreToolUse hook for Claude Code and Codex CLI.
  - Deterministic regex filtering for high-blast-radius commands.
  - Secret redaction (tokens, PATs, bearer headers) before Jev evaluation.
  - Dual mode: `--shadow` (append to `.local/sentinel.jsonl`) and `--gated` (prompt user on conflict/ambiguous).
  - Explicit evaluation of active constraints (`CONSTRAINTS.md` or system prompt rules).
- **Out**:
  - Arbitrary bash code sandboxing or kernel-level tracing.
  - Blocking non-destructive commands (`cat`, `ls`, `grep`, `pytest`).
  - Granting permissions autonomously (Scope Sentinel can only warn or flag, never authorize).

## Not Doing (and Why)
- **Not checking every bash command**: Running LLM inference on `ls`, `pwd`, or `git status` burns money and kills performance. Only consequential actions get judged.
- **Not allowing Jev to grant permission**: Jev is an advisor, not a root security authority. Failsafe default is always fail-open in shadow mode, or escalate to human in gated mode.

## Open Questions
- What is the ideal transcript window size (e.g., last 3 user turns vs. 1 user turn) to prevent false conflicts on multi-step workflows?

---

### One-Pager 3: Handoff Integrity Check

# Handoff Integrity Check

## Problem Statement
How might we prevent multi-agent workflows and long sessions from losing critical constraints and misrepresenting unfinished work during context compactions and task handoffs?

## Recommended Direction
Position Handoff Integrity Check as the synchronization validator between a project's decision/constraint ledger (e.g. `CONSTRAINTS.md`, MemPalace shared logstream, or ADRs) and an agent's transition handoff.

When an agent finishes a subtask, generates a handoff report, or triggers context compaction, the tool compares each active constraint or ledger item against the generated summary in a single batch Jev query. It flags constraints dropped entirely (`missing`), unfinished items claimed as complete (`falsely_complete`), or altered parameters (`changed`).

## Key Assumptions to Validate
- [ ] **Paraphrase Resilience**: Jev can recognize that a differently phrased handoff still faithfully preserves a constraint without triggering a false `changed` alert. *Test: Evaluate 40 pairs of identical constraints expressed in diverse natural language.*
- [ ] **Batch Scalability**: Evaluating 10-15 ledger items in a single Jev Choice payload remains reliable and within token bounds. *Test: Measure Jev latency and answer quality with 5, 10, and 20 ledger items.*

## MVP Scope
- **In**:
  - Plaintext/Markdown ledger parser (`parse_ledger`).
  - Multi-question Jev evaluator assessing all ledger items against handoff text.
  - CLI utility: `handoff_check.py --ledger <path> --handoff <path>`.
  - Structured output (`INTACT`, `MISSING`, `FALSELY_COMPLETE`, `CHANGED`).
- **Out**:
  - Dynamic graph database or heavy requirements tracking suites.
  - Automatic hallucination rewriting (strictly flags for user/parent agent awareness).

## Not Doing (and Why)
- **Not building a proprietary ledger format**: Uses plain markdown lists or existing repo files (`CONSTRAINTS.md`). No custom DB required.
- **Not validating code diffs**: That is the job of Test Escrow and Drift Radar; Handoff Check focuses exclusively on task prose continuity.

## Open Questions
- Should Handoff Check run as a pre-compact hook in Claude Code, or as an inter-agent message interceptor in multi-agent frameworks like MemPalace?

---

## 5. Explicit "Kill" Item: Smart Reader

### Post-Mortem & Decommissioning Rationale
`smart_reader.py` splits text files into 50-line overlapping chunks and calls Jev sequentially on each chunk to determine relevance.

**Why it must be killed:**
1. **Economic Inversion**: Evaluating a 1,000-line file requires 25 sequential Jev API calls. At ~200 input tokens per call, that's 5,000 tokens and 25 round trips (~30–50 seconds). Injecting the entire file into Claude 3.5 Sonnet or Gemini 1.5/2.0 costs fractions of a cent and takes <1 second.
2. **Syntactic Decapitation**: 50-line chunks cut across functions, classes, and scopes. Returning sliced chunks with `... [lines omitted] ...` breaks code syntax and strips imports and type definitions required for LLM reasoning.
3. **Solved Problem**: Deterministic tools (`ripgrep`, `ctags`, LSP symbol navigation) locate relevant code in milliseconds for zero cost.
