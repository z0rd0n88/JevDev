# Idea Nebula: new Jev features for Alex's Claude Code / Codex / agy workflow

**Date:** 2026-10-31

**Status:** Brainstorm output with live demand evidence; nothing below is built, calibrated, or validated in production. Builds on the 2026-09-27 [`jev-idea-nebula.md`](jev-idea-nebula.md) and [`jev-feature-opportunities.md`](jev-feature-opportunities.md), which predate the installed gates and the shadow log.

Four parallel runs (code quality, security, speed, token cost). Each run: 4 blind generators (tails, folk, alien, miner), one blind ranker with both-order duels, live demand-checks on the top 5 finalists. Input context: 30 days of transcripts (1,114 sessions, 15,530 Bash calls, 781 subagent spawns), the 30k-row Jev shadow log, and git history of 12 repos. Pool: 92 ideas, 32 finalists, 20 demand-checked.

## Cross-run summary

Five ideas were reached independently by more than one run. Those are the strongest signal in the whole exercise:

1. **Review triage inside the loop** (speed: Finding Triage and Convergence; tokens: Review Lanes with Re-Review Skip). Both GROUNDED, gap 24 and 20. Jev grades findings and picks lanes so the review→fix→re-review loop stops burning full fan-outs. This is the single best-evidenced build.
2. **Spawn gating on the Agent call** (speed: Spawn Dispatcher; tokens: Spawn Tax). GROUNDED, gap 16, 42 complainants. Jev prices a subagent before it runs and rewrites model/effort or refuses it.
3. **Undo instead of block** (security: Dead-Man's Stash, GROUNDED gap 25) paired with **the retry after a block** (security: Second Try, GROUNDED gap 16). Together they replace "deny" with "snapshot, then watch what the agent does next".
4. **Keep secrets out of the transcript** (security: Redact-at-Source, GROUNDED gap 20). Rewrite the command so the value never prints.
5. **Per-situation output narrowing** (tokens: Verbatim-or-Vault, GROUNDED gap 16). The judgment rtk and context-mode lack.

Two popular finalists died on evidence: Fire the Allowlist (vendor shipped compound-command splitting in Aug 2026) and Skill Roster Diet (`/skill-doctor` is built in; KILL-ZONE).

---

# Run 1: improve code quality

## Executive Summary
4 generators, 23 ideas, 8 finalists, 5 demand-checked live. Most promising safe pick: **Stowaway Hunks** (GROUNDED, gap 24, six shipped tools all gate on file paths and none scores hunks against the request). Most interesting moonshot: **Mutant Oracle** (predict mutation kills with Jev, run pitest only on predicted survivors; lost every duel on plausibility, kept for distance).

## Safe Picks
1. **Stowaway Hunks** — Stop hook scores every hunk in the working diff for "does this trace back to the request", names the stowaways, can quarantine them into a separate patch. 2-2-3. Novelty: one step past the "unrequested-change detector" trope via per-hunk tracing and `git apply -R` quarantine. Why now: Stop hooks carry `transcript_path` and can block with a reason. Founder fit: compaction-advisor Stop scaffolding plus stdlib diff parsing; shadow `stowaways.jsonl` first. Risk: multi-turn requests make honest hunks score low. Demand: **GROUNDED, gap 24**, ~30 complainants ("who told you to do that?"), six vendors all path-allowlist based.
2. **Code Passport** — per-repo rolling baseline (median + MAD) of test-strength, suppression rate, prime-directive breaches and slop density per edit; flags drift from the repo's own normal. 5-2-0. Novelty: replaces the fixed bar every trope uses with a longitudinal profile. Why now: per-edit scoring is free at Jev prices; PostToolUse delivers old/new strings. Founder fit: one PostToolUse hook writing `passport.jsonl`; VistaMobileBE builds a baseline in a week. Risk: a slop-prone baseline normalises slop; needs an absolute floor on suppressions. Demand: **GROUNDED, gap 20**, 24 complainants, 5 vendors (Evolution Engine is commit-granular, sentrux structural-only, constraint-driven-development is prose).
3. **Stub Smuggler Alarm** — detects "compile error, then hardcoded mock/fallback in production code" and denies the edit until the agent reads the type it was fighting. 5-1-1. Novelty: judges a two-turn causal pattern, not one hunk. Why now: PreToolUse deny-with-reason; Kotlin/TS compilers name the symbol. Founder fit: one state field plus two questions on the write gate. Risk: DI test doubles and feature flags look identical. Demand: **GROUNDED, gap 16**, 28 complainants. Correction from the check: PreToolUse does not receive the prior tool result; a PostToolUse companion must cache the last failed Bash result to disk.
4. **Alibi Check for "pre-existing"** — when the agent calls a failure pre-existing or flaky, Jev scores the causal link to the session diff and blocks the stop until a base-branch run is shown. 5-2-0 (duel winner). Novelty: targets the one sentence where bugs get waved through. Why now: worktree-per-session makes the base comparison one command. Founder fit: failure-signature regexes for Gradle/pytest/flutter; shadow on last month's ~15 "pre-existing" claims. Risk: flaky suites make the comparison flaky. Demand: **WEAK, gap 16**: ~20 complainants, no paid vendor, free regex Stop hooks already ban the phrase; Jev's slice is the causal scoring that avoids false positives. Use `git worktree` not `git stash` for the comparison (stash drops are a documented agent data-loss vector).
5. **Receipt or It Didn't Happen** (CONVERGENT, 4 generators) — Stop hook refuses to end a turn on "tests pass" unless the transcript holds the command that could prove it; stamps a claim→command→exit-code table into the PR body. 1-3-3. Novelty: inside the modal region; the receipt table and SubagentStop coverage are the non-obvious parts. Why now: Stop can block; METR's ~30% reward-hacking rate. Founder fit: transcript parser exists. Risk: tests run in subagents or Workflow steps are invisible to the parent transcript. Demand: **UNVERIFIED** (outside the top-5 check).

## Moonshots
High-variance bets kept because they are far from the modal region; expect most to die under validation.
1. **Lookback Retesting** — every `fix:` commit becomes a labelled sample; re-score the bug-introducing diff with every current Jev question and report recall per question. 1-4-2. Novelty: judges the judge. Why now: cheap re-scoring. Founder fit: CLI next to `ask_jev_files.py`, start on VistaMobileBE's 29 fixes. Risk: label noise. Demand: **DOWNGRADE, gap 12**: only 4 direct complainants; vendors (Greptile, Tenki) ship self-favouring replay benchmarks, nobody sells per-repo replay. Note: "AI commits are conventional-commit tagged" is only true where CLAUDE.md enforces it.
2. **Pre-Filed Exemptions (TUE)** — the agent may break a guarded rule only by filing a justification first; Jev checks the filing covers the actual act. 1-2-4. Novelty: binary guards become conditional. Risk: exemption abuse as step one of every task. Demand: **UNVERIFIED**.
3. **Mutant Oracle** — generate trivial mutants by text substitution, ask Jev which the test file would catch, run real pitest only on predicted survivors, flag decorative tests. 0-0-7. Novelty: scores what a test would catch, not the test. Risk: it is simulation, not judgment; calibration never gets checked. Demand: **UNVERIFIED**.

## Demand Evidence
| Idea | Independent complaints | Existing paid vendors | Gap | Flags |
|---|---|---|---|---|
| Stowaway Hunks | ~30: "The agent routinely touches unrelated files, removes comments, fixes unrelated TypeScript errors" (Cursor forum 165633); "Claude Code does more than I asked" (claude-code#89579) | Cursor review, CodeRabbit out-of-scope check, scopediff, guard-dog, over_reach_detector | 4×6=24 | GROUNDED |
| Code Passport | 24: "If the same agent writes the tests and the code, it will happily weaken an assertion, add a skip" (HN 50149155); claude-code#319, #45550 | Evolution Engine, sentrux, drift-analyzer, constraint-driven-development, PR bots | 4×5=20 | GROUNDED |
| Stub Smuggler | 28: "Claude cheats constantly at the tests ime. It frequently tests the mock instead of the UUT" (HN 45519398); claude-code#2345, #6984 | agent-guard-hooks (tests only), output-validator (warn only), CLAUDE.md prose | 4×4=16 | GROUNDED; PreToolUse lacks prior tool result |
| Alibi Check | ~20: "calmly resolves it with a declaration that it was a 'pre-existing failure'" (HN 47866414); claude-code#59293 closed NOT_PLANNED | None paid; free regex hooks stop-phrase-guard, no-vibes, prove-pre-existing skill | 4×4=16 | WEAK |
| Lookback Retesting | 4 direct (35 adjacent on review-gate noise) | Greptile/Tenki/Entelligence benchmarks (vendor-run) | 3×4=12 | DOWNGRADE |
| Receipt, TUE, Mutant Oracle | not checked | | | UNVERIFIED |

## Modal Region (what we refused to rank as novel)
Any single-pass brainstorm on "LLM-judge for AI-coding quality" lands on the same six tropes: a per-edit linter-with-a-model that scores the diff for bugs and style, an end-of-turn verifier that checks "tests pass" against the transcript, a rule-compliance checker that re-injects or grades CLAUDE.md/AGENTS.md adherence, a test-quality scorer that flags tautological or mocked tests, a PR triage router that picks review depth, and a quality dashboard of those numbers. Everything in that region is a judgment applied to one artifact at one fixed moment against one fixed bar.

## Convergence & Disagreement
- Receipt or It Didn't Happen: miner (lead), alien (Entourage Liability), tails (Polygraph at Stop), folk (Claim Ledger at Stop). Four of four generators.
- Stowaway Hunks: tails (Stop seam) + folk (Hunk-vs-Issue pre-commit).
- Test-bending at write time: folk (Fitted-Assertion Gate) + miner (Assertion Worth Ledger); pruned as dominated by Stub Smuggler.
- Disagreement: the ranker put Alibi Check first; the demand-check downgraded it to WEAK because free regex hooks already own the blocking half. The ranker's 1-3-3 Receipt idea is what four generators and the complaint corpus actually want.

## Validate Next
- Stowaway Hunks: one week of shadow `stowaways.jsonl` on VistaMobileBE sessions; count stowaway hunks per PR and hand-label 30 of them. Act only if precision is over 0.8.
- Mutant Oracle: run the predictor on 5 Kotest files, then run real pitest on the same files once and compare predicted vs actual kills. If agreement is under 0.7, drop it.

## Final Cut Is Yours
This ranking is a funnel, not a verdict. In the only RCT that built ideas out (~100 expert-hours each), LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment — especially between the barbell's two ends.

---

# Run 2: minimize security errors and risk

## Executive Summary
4 generators, 24 ideas, 8 finalists, 5 demand-checked. Most promising safe pick: **Redact-at-Source** (GROUNDED, gap 20, ~38 complainants, five vendor classes all leave the pre-execution seam untouched). Most interesting moonshot: **Second Try** (GROUNDED, gap 16; judges the retry after a block, which nothing logs). Dead-Man's Stash won every duel but two open-source hooks already snapshot before destructive commands, so its defensible slice is narrow.

## Safe Picks
1. **Dead-Man's Stash** (CONVERGENT with Snapshot Before Strike) — never block a destructive git/rm command; ask Jev whether it discards work nothing else holds, snapshot the tree into a hidden ref, let it run; `jev-undo` restores. 6-1-0. Novelty: makes the irreversible undoable instead of blocking. Why now: PreToolUse can snapshot and soften in one pass; the sentinel log has 221 irreversible rows to backtest. Founder fit: one hook plus a CLI subcommand. Risk: `git stash create` misses untracked files; a half-snapshot is worse than none. Demand: **GROUNDED, gap 25** with a narrow-gap warning: claude-oops and git-safepoint already snapshot on PreToolUse via regex lists. Jev's slice is the unheld-work judgment and the regex-miss gap (claude-code#97881).
2. **Hemovigilance Register** — weekly CLI adjudicates every shadow `would_block` row against what happened next, computes precision per block-reason template, flips gates from shadow to act one template at a time above 0.9. 5-2-0. Novelty: the thing that decides how shadow mode ends. Why now: 1,400 would_block verdicts exist and nobody has read one. Founder fit: adjudication pass first, no `act.json`. Risk: "what happened next" is weak ground truth. Demand: **DOWNGRADE, gap 9**: only 5 direct complainants ("A 90% accurate guardrail is a user-blocking machine"); vendors ship shadow modes, none ships measured promotion; no budget line.
3. **Redact-at-Source** — before a Bash command runs, Jev judges whether its output will print credentials; the hook rewrites the command via `updatedInput` so values are masked before they enter the transcript; a taint ledger records which session files would have held which key names. 5-1-1. Novelty: rewrite, not deny; answers "which surface leaked". Why now: `updatedInput` is live; transcripts and file-history are a 2026 leak wave. Founder fit: your environment-facts rule already does this by hand with `sed 's/=.*/=<set>/'`. Risk: over-masking breaks JWT debugging. Demand: **GROUNDED, gap 20**, ~38 complainants ("I still had 600 secrets in plaintext", claude-code#63593 closed without fix).
4. **Cash Cage** — Edit hook on money paths classifies each hunk by direction of funds; dual control only on outgoing-custody hunks; float in money math blocked. 3-1-3. Novelty: the direction asymmetry. Why now: withdrawals and MoonPay on-ramp shipped this quarter. Founder fit: `ask_jev_files.py hunks` subcommand on the withdrawal retro diff. Risk: confirmation fatigue. Demand: **DOWNGRADE, gap 8**: 8 complainants, and every loss with a URL happened at transfer execution, not at Edit. The check recommends re-aiming at a PreToolUse Bash gate on outgoing transfers (the claude-code#21774 ask) and folding the float ban into `audit-numeric-types`.

## Moonshots
High-variance bets kept because they are far from the modal region; expect most to die under validation.
1. **Second Try** — fires only when the previous command was blocked; asks whether the new command is the same action re-worded to dodge the guard; evasions hard-blocked and logged. 3-1-3. Novelty: judges the retry, a turn nobody logs. Why now: `PermissionDenied` hook with `retry` landed v2.1.88; Backslash measured 8 of 8 denials rerouted. Founder fit: per-session state file plus three recorded block/retry pairs. Risk: most retries are legitimate. Demand: **GROUNDED, gap 16**, 27 complainants ("the Bash tool with tee would achieve the same file write while bypassing the hook entirely"). Design caveat: `PermissionDenied` does not fire for PreToolUse or deny-rule blocks, so the hook must record its own blocks, and a Bash→Write reroute needs the hook on Write/Edit too.
2. **Silhouette** — replace high-entropy tokens with shape descriptors (`<HEX:64>`, `<JWT 3-part>`) inside `jev_patterns.call` before anything goes to OpenRouter; then gate pastes, writes and commits on the silhouette. 1-1-5. Novelty: fixes a leak in the existing gate rather than adding a gate. Risk: a fixture's fake 64-hex and a real private key look identical. Demand: **UNVERIFIED**.
3. **Say-Do** — reads the assistant's last narration and asks whether the command does what the sentence says. 0-2-5. Novelty: catches hallucinated and injected actions as divergence. Risk: terse narration gives nothing to grip. Demand: **UNVERIFIED**.
4. **Who Told You That** — tag imperatives in pasted/fetched text, then at Stop attribute each write/commit/push to user, paste, page or PR comment. 0-1-6. Novelty: audits obedience instead of blocking on the way in. Risk: attribution noise. Demand: **UNVERIFIED**.

## Demand Evidence
| Idea | Independent complaints | Existing paid vendors | Gap | Flags |
|---|---|---|---|---|
| Dead-Man's Stash | 34: "ran `git reset --hard origin/main` autonomously within the first second of session startup on two separate occasions" (claude-code#34327) | /rewind (ignores Bash), auto-mode classifier, Cursor checkpoints, claude-oops, git-safepoint, Unfucked | 5×5=25 | GROUNDED, narrow gap |
| Redact-at-Source | ~38: "records tool stdout verbatim... durably on disk with no built-in redaction" (claude-code#63593) | Anthropic shared-only redaction, PostToolUse scrubbers, Sieve-style scanners, vault brokers, Cursor ignore | 4×5=20 | GROUNDED |
| Second Try | 27: "Nine times the same change reached the disk seconds later by another route" (Backslash) | Anthropic denial valve, regex guard family, Codex/Cursor allowlists, rtk | 4×4=16 | GROUNDED |
| Hemovigilance Register | 5 direct: "deployed a guardrail that flagged 30% of legitimate interactions and the teams started routing around it" (r/LLMDevs) | shadow modes in OrcaRouter, Strands, Writer; none promote | 3×3=9 | DOWNGRADE |
| Cash Cage | 8: "sent 3.086 SOL to an incorrect wallet address... a missing 'u' character" (claude-code#21774) | Coinbase Agentic Wallets, Circle policies (runtime); path-based edit hooks | 4×2=8 | DOWNGRADE, re-aim at runtime |
| Silhouette, Say-Do, Who Told You That | not checked | | | UNVERIFIED |

## Modal Region (what we refused to rank as novel)
A generic single-pass brainstorm on "LLM judge for agent security" lands on five tropes: a secret-pattern scanner on writes/commits/outputs, a dangerous-command blocklist on PreToolUse (`rm -rf`, `git reset --hard`), an "ignore previous instructions" detector on fetched/tool output that flags or denies, a dependency-install vetting check (age, downloads, typosquat distance), and a money-code linter that greps for floats in amount math. All of them block on the way in, judge each event in isolation, and treat the repo or the command as the thing to protect rather than the transcript, the retry, the narration, or the shadow log itself.

## Convergence & Disagreement
- Dead-Man's Stash: miner + folk (Snapshot Before Strike).
- Install gate: miner (Install Bouncer) + folk (Lookalike); pruned as modal.
- Money-path edit gate: alien (Special Requirements Flag) + miner (Lot-Size Lie Detector); pruned, Cash Cage kept, then downgraded.
- Injection taint: folk (Taint Window) + miner (Taint Trail) + alien (Irradiated Output); pruned as modal in favour of Say-Do and Who Told You That.
- Leak ledger: tails (Leak Ledger) + alien (Lookback); pruned in favour of Silhouette.
- Disagreement: the ranker's second safe pick (Hemovigilance) is the one the market has no budget for; the ranker's fifth-place moonshot (Second Try) is better grounded than two of the safe picks.

## Validate Next
- Redact-at-Source: replay the 30,458 sentinel commands offline and count `would_rewrite`; hand-check 50 rewrites for over-masking. Ship in shadow if under 5% of rewrites would have hidden something the agent needed.
- Second Try: pull every block/retry pair from last month's transcripts (the ~195 guard blocks plus 94 classifier denials) and label 40 by hand as evasion or genuine fix. Act only if Jev agrees with the labels above 0.85.

## Final Cut Is Yours
This ranking is a funnel, not a verdict. In the only RCT that built ideas out (~100 expert-hours each), LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment — especially between the barbell's two ends.

---

# Run 3: speed up development

## Executive Summary
4 generators, 23 ideas, 8 finalists, 5 demand-checked. Most promising safe pick: **Finding Triage and Convergence** (GROUNDED, gap 24, three generators converged, six vendors fail at per-finding provenance). Most interesting moonshot: **Sealed Baton** (per-claim seals on handoff notes bound to blob hashes; furthest from modal, lost every duel). The duel winner Fire the Allowlist was downgraded: Anthropic shipped compound-command splitting in Aug 2026 and the surviving pain is a different problem.

## Safe Picks
1. **Finding Triage and Convergence** (CONVERGENT ×3) — before each re-review round, Jev grades every finding (introduced by this diff via blame? duplicate of a prior round? severity? mechanical?), picks the keystone finding, skips the fan-out for mechanical fixes, stops the loop at zero new HIGH. Reorders and labels, never deletes. 5-2-0. Novelty: scores novelty across rounds; stop condition becomes "converged". Why now: loop-by-default in multi-agent-review 2.0. Founder fit: `findings` subcommand run over the last 10 saved reviews in `docs/reviews/`. Risk: a restated finding is sometimes the signal the fix was wrong. Demand: **GROUNDED, gap 24**, 27 complainants; "False convergence" is named verbatim by a practitioner running the same loop.
2. **Hook Appeals Court** (CONVERGENT ×3) — every regex guard asks Jev for a 300 ms second opinion before exit 2; overturns logged; weekly job proposes the narrower regex; secrets-guard may only downgrade to a warning. 5-2-0. Novelty: retire the regex, not add a gate. Why now: auto-mode prompt pushes cat/sed/heredocs, so guards written for clean commands misfire more. Founder fit: wrap `merge-guard.py`'s block path first, shadow against its 54 logged blocks. Risk: a 0.35 threshold on secrets-guard is a rotation incident. Demand: **GROUNDED, gap 16**, 32 complainants, with two cuts: ~75% of the loud complaints are about Anthropic's built-in worktree guard, which runs after hooks and cannot be appealed; and the most-upvoted ask wants fewer LLM judgments in the hook path.
3. **Déjà-Vu Guard** — file every subagent report and completed irreversible command; after compaction or on any new spawn, Jev checks whether the proposed action duplicates filed work (with files-changed-since in the state) and hands back the stored result. 4-0-3. Novelty: acts after compaction on what not to redo. Why now: SessionStart(compact) and PostToolUse on Agent exist; 781 spawns a month. Founder fit: PostToolUse Agent filer plus replay over the 58 compaction boundaries. Risk: a legitimate re-run blocked as duplicate. Demand: **GROUNDED, gap 16**, 33 complainants ("The backend review agent's results were lost during context compaction. Let me re-run it"); vendor-fix risk flagged (a harness bug Anthropic could close any week); open bug #91910 makes SessionStart(compact) misfire inside subagents.
4. **Spawn Dispatcher** (CONVERGENT ×2) — PreToolUse on Agent scores difficulty on a 4-rung rubric, refuses spawns a Grep would answer, rewrites model/effort for mechanical work. 1-2-4. Novelty: squarely modal except the "don't spawn, Grep instead" veto. Why now: Agent takes `model` and `effort` per call; 10× price spread. Founder fit: replay the 781 prompts and compare predicted class to actual spend. Risk: a downgraded builder ships worse code. Demand: **GROUNDED, gap 16**, ~42 complainants ("launched 7 sub agents which burned through my budget"). Cut the Skill-sibling veto: zero complaint evidence. Watch #100701: `effort` is dropped for named in-process teammates.
5. **Fire the Allowlist** (CONVERGENT with Green Lane) — PermissionRequest hook splits compound commands, scores each segment, auto-allows read-only or reversible-and-covered segments; earned per-(repo, family) trust lanes. 5-2-0 (duel winner). Novelty: modal at its core. Why now: PermissionRequest hook event. Founder fit: shadow hook replayed against sentinel.jsonl. Risk: one false allow on an irreversible command. Demand: **DOWNGRADE, gap 9**: claude-code#16561 closed completed 2026-08-17 with native `&&`/`;`/`|` splitting; free native auto mode covers most users; the one issue asking for exactly this (codex#50572) drew zero votes. Residual niche: people who reject auto mode on principle, and agy, which has no auto mode.

## Moonshots
High-variance bets kept because they are far from the modal region; expect most to die under validation.
1. **Fairway Pilot** — PostToolUse hook reads the last 15 calls, asks Jev which phase the session is in, and on a phase change injects the mandatory next move (review skill, merge cleanup, worktree teardown, or the matching gotcha paragraph after a guard block). 1-2-4. Novelty: routes on position, not prompt. Risk: nagging; cooldown and confidence floor are the whole product. Demand: **UNVERIFIED**.
2. **Short-Landed Report** — SubagentStop hook asks whether the report answers the brief and whether the gap is one SendMessage away; routes to a continuation instead of a respawn; pre-dispatch brief-completeness check. 0-3-4. Novelty: reconciliation at discharge. Risk: hook point may fire on the spawn acknowledgement, not the result. Demand: **UNVERIFIED**.
3. **Sealed Baton** — `ask_jev_files.py seal baton.md` stamps each supported claim with a seal bound to blob hashes; the receiving session re-hashes and injects "sealed, do not re-read / unsealed, verify first". 0-1-6. Novelty: persistence design, reader side makes no Jev call. Risk: claims that name no file can never be sealed. Demand: **UNVERIFIED**.

## Demand Evidence
| Idea | Independent complaints | Existing paid vendors | Gap | Flags |
|---|---|---|---|---|
| Finding Triage | 27: "adds too much noise to PRs... instructed it to ignore nitpicks, but it still added such comments" (HN 42484498); "False convergence" (Vaughan) | CodeRabbit, Greptile, Copilot review (auto-resolve since Sept 2026), Bugbot, Claude Code Review, OSS loops | 4×6=24 | GROUNDED |
| Hook Appeals Court | ≥32: "grep -n 'git-commit-id' is refused: the quoted grep pattern is treated as a git invocation" (claude-code#100806) | Anthropic classifier/worktree guard, ccgate, cc-safety-net, cc-safe-setup, secret scanners | 4×4=16 | GROUNDED; built-in guard unreachable |
| Déjà-Vu Guard | 33: "re-runs the full test suite even when tests were already run... no code changes occurred" (claude-code#27648) | Anthropic PostCompact, claude-mem, Cozempic, Codex (open #29356) | 4×4=16 | GROUNDED; vendor-fix risk |
| Spawn Dispatcher | ~42: "All 46 subagents ran on Opus... no automatic downgrade" (claude-code#66023) | Anthropic static per-agent model/effort, workweave router, Rayline, nedjamez hook | 4×4=16 | GROUNDED; cut skill veto |
| Fire the Allowlist | ~35, mostly pre-Aug 2026: "I had to babysit it for hours today because it insisted on prefixing every command with `cd blah &&`" (claude-code#16561, now closed) | Anthropic native splitting + auto mode, Codex execpolicy, mutgarth/automode | 3×3=9 | DOWNGRADE |
| Fairway Pilot, Short-Landed Report, Sealed Baton | not checked | | | UNVERIFIED |

## Modal Region (what we refused to rank as novel)
The obvious single-pass brainstorm on "Jev for faster Claude Code" is gate-wrapping: put one noul in front of each existing yes/no gate (permission prompt, regex guard, subagent spawn, AskUserQuestion, review-finding severity, "is the agent looping") and threshold it, with a shadow log first. Its tropes are the auto-approve classifier that replaces the allowlist, the model/effort router at the Agent call, the "answer the question yourself" gate, the thrash detector, and the finding-severity triage. Anything whose whole contribution is "same gate, now a probability instead of a regex" sits inside it.

## Convergence & Disagreement
- Hook Appeals Court: miner + folk (Manager Override Code) + tails (Guard Appeals Court). All three independently excluded secrets-guard from silent pass-through.
- Finding Triage: miner + tails (Review-Loop Terminator, keystone pick) + folk (Auto-Pay Findings).
- Spawn routing: miner (Spawn Dispatcher) + folk (Green Lane for Spawns).
- Allowlist replacement: miner (Fire the Allowlist) + alien (Green Lane).
- Self-answering questions: miner (Self-Answering AskUserQuestion) + tails (Default-It Stop Gate); pruned.
- Churn detection: tails (Fresh-Eyes Ejection Seat) + folk (Three-PIN Lockout); pruned in favour of Fairway Pilot.
- Disagreement: the miner's own why-now for Fire the Allowlist ("among the most-upvoted open issues") was wrong; the issue closed two months before the run.

## Validate Next
- Finding Triage: run the `findings` subcommand over the last 10 saved review reports and join to finding-fixer's SUPPORTED/REFUTED verdicts; report precision of "duplicate" and "pre-existing" labels. Act only if both are above 0.85.
- Sealed Baton: seal the next 5 batons by hand with the subcommand and count how many seals are still intact when the receiving session opens them. If under half survive, the blob-hash keying needs rethinking before any hook.

## Final Cut Is Yours
This ranking is a funnel, not a verdict. In the only RCT that built ideas out (~100 expert-hours each), LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment — especially between the barbell's two ends.

---

# Run 4: reduce token cost

## Executive Summary
4 generators, 22 ideas, 8 finalists, 5 demand-checked. Most promising safe pick: **Review Lanes with Re-Review Skip** (GROUNDED, gap 20; "$15-25 per PR" threads with 285 points, five vendors bill per run and none routes by risk). Most interesting moonshot: **Cache Warm-Keeper** (GROUNDED, gap 16; best duel record in the pool, placed as a moonshot because it bets on billing mechanics rather than shrinking context). The duel winner Skill Roster Diet is a KILL-ZONE: `/skill-doctor` ships in the harness.

## Safe Picks
1. **Review Lanes with Re-Review Skip** (CONVERGENT ×4) — pre-push plus first step of the review skills: Jev scores diff risk and picks lanes {none, standards, correctness+tests, security+money, full panel}; money/auth paths always force the security lane; after a fix round, "fix stayed within findings" sends one verifier instead of a full re-review; a seeded 1-in-20 full audit on skipped PRs keeps the classifier honest. 2-3-2. Novelty: the random audit ratchet lifts it out of the "lighter review" trope. Why now: per-push looping review became the billing unit in 2026. Founder fit: dry-run CLI over the last 30 merged PRs vs what actually ran. Risk: skipping a lane on a diff that silently touched a money path. Demand: **GROUNDED, gap 20**, ~23 complainants ("$75-250/day, potentially $1500-5000/month just for reviews").
2. **Verbatim-or-Vault** (CONVERGENT ×4) — PreToolUse on Bash and whole-file Reads asks Jev per situation whether the agent needs the output verbatim, derived only, or already has it; rewrites large derive-only output to a scratch file with a summary line, narrows Reads to the section Jev picks, always passes failure output verbatim, refuses already-read files with the turn and line range. 2-3-2. Novelty: per situation, not per command type. Why now: `updatedInput`; rtk proved the saving and the failure mode. Founder fit: three more questions on the existing bash gate, replay against 30k rows. Risk: vaulting the one output the agent needed. Demand: **GROUNDED, gap 16**, ~24 complainants; rtk's top issue is "+18% cost because compressed output forces 50% more output tokens". Must surface what it did via `additionalContext` or it inherits rtk's failure.
3. **Spawn Tax** (CONVERGENT ×3) — PreToolUse on Agent prices every spawn: `inline_doable`, tier, brief quality, will-reread-parent-files; denies or rewrites model/effort. 0-2-5. Novelty: modal router trope with a brief-quality score. Why now: `updatedInput` on Agent calls; per-subagent usage in local JSONL. Founder fit: replay script over 781 prompts. Risk: wrongly downgraded builder. Demand: **UNVERIFIED** in this run, but the near-identical Spawn Dispatcher was checked in the speed run: GROUNDED, gap 16.
4. **Salvage List** (CONVERGENT ×2) — PreCompact hook ranks which tool outputs and decisions must survive compaction under a hard token budget, writes `salvage.md`, re-injects it at SessionStart(compact); plus a "standing orders" block of still-binding user prompts. 0-1-6. Novelty: targets the one compaction channel issue #89797 showed survives. Why now: PreCompact and SessionStart(compact) exist. Founder fit: offline score of one compacted session's chunks vs what the agent re-read in the next 20 turns. Risk: over-salvaging reinflates the context. Demand: **UNVERIFIED**.
5. **Skill Roster Diet** (CONVERGENT ×2) — nightly CLI scores every skill description against 30 days of prompts and proposes demotions with tokens-saved-per-turn. 6-1-0 (duel winner). Demand: **KILL-ZONE, gap 6**: `/skill-doctor` (v2.1.252+, installed here is 2.1.316) already reports per-skill cost, invocation count and last use; `skillOverrides: name-only` already drops the description per current docs; codeprakhar25/optimize does the JSONL-grep proposal for free. The idea's premise that `skillOverrides` keeps the description in the listing is contradicted by current docs and should be re-verified in your AGENTS.md. Do not build; run `/skill-doctor` instead.

## Moonshots
High-variance bets kept because they are far from the modal region; expect most to die under validation.
1. **Cache Warm-Keeper** — PreToolUse backgrounds commands Jev predicts will outlive the cache TTL when the result is not needed before the next step; Stop hook prints the computed rewrite cost when you look like you are leaving a large session. 6-1-0 (best record in the pool). Novelty: moves work in time instead of shrinking anything. Why now: 1-hour main / 5-minute subagent TTLs; `cache_creation` fields in transcripts. Founder fit: find last month's >100k rewrites and join to the preceding Bash command. Risk: backgrounding a command whose output the next step needs. Demand: **GROUNDED, gap 16**, ≥80 complainants ("Median Bash duration for those calls 600 s... 92% of the rewritten tokens", claude-code#99808). The Stop-hook half is crowded (10+ keepalive repos); the defensible part is the PreToolUse backgrounding, which nobody ships. Note: past Bash durations in your own transcripts predict better than Jev here.
2. **Injection Toll Booth** — UserPromptSubmit wrapper runs your own injectors and drops the ones Jev says this prompt cannot use; safety injections never gated. 2-3-2. Novelty: gates what the harness prepends. Risk: suppressing the one injection the prompt needed. Demand: **WEAK, gap 9**: ~22 complainants on the general cache-read tax but only ~6 on user-owned injectors; the wrapper can touch only ~15% of fixed overhead; ai-nexus already occupies the seam with GPT-4o-mini.
3. **LCL Consolidation** — after three consecutive orientation probes (ls, cat, grep, git log) Jev classes as open-ended, block the fourth with "write the rest as one script or one `ctx_batch_execute`". 1-4-2. Novelty: behavioural intervention across calls. Risk: a wrong block adds a turn. Demand: **UNVERIFIED**. Cheap kill test: measure the distribution of consecutive read-only runs per session in sentinel.jsonl; if the median run is 2, drop it.

## Demand Evidence
| Idea | Independent complaints | Existing paid vendors | Gap | Flags |
|---|---|---|---|---|
| Review Lanes | ~23: "Two reviews totaled $214.43" (claude-code#34114); "no way to unsubscribe... runaway cost on active PRs" (#60723) | Anthropic Code Review, Copilot review, CodeRabbit, Greptile, Bugbot | 4×5=20 | GROUNDED |
| Verbatim-or-Vault | ~24: "RTK Hook Increases Claude Code Costs by 18%" (rtk#582); codex#55684 "repeated truncation and rereads" | rtk, context-mode, Context Gateway, Claude Code native truncation | 4×4=16 | GROUNDED |
| Cache Warm-Keeper | ≥80: "some sessions cost like 10x what they should because of cold caches" (HN 50238655) | Anthropic TTL settings and idle compaction, keepalive plugin cluster, Codeman | 4×4=16 | GROUNDED |
| Injection Toll Booth | ~22 general / ~6 specific: "Cache reads as % of total: 99.93%" (claude-code#24147) | ai-nexus, unclog, Anthropic manual controls | 3×3=9 | WEAK |
| Skill Roster Diet | ~30: "2,596 skills installed... 102,651 tokens loaded into every session" (r/ClaudeAI) | Anthropic `/skill-doctor` built in; skills-janitor, optimize, skill-graveyard | 3×2=6 | KILL-ZONE |
| Spawn Tax, Salvage List, LCL Consolidation | not checked (Spawn Tax's sibling GROUNDED in run 3) | | | UNVERIFIED |

## Modal Region (what we refused to rank as novel)
A generic single-pass brainstorm on "use a cheap classifier to cut agent token cost" produces five tropes: truncate or summarize tool output before it enters context (tail the build log, push it to a sandbox), gate or down-tier subagent spawns onto cheaper models, run a lighter review on low-risk diffs, prune the always-loaded prefix (unused skills, MCP tool descriptions), and make compaction keep the right things; plus the after-the-fact usage dashboard (ccusage, CodeBurn). Anything shaped "classify at an obvious choke point, then shrink it" is MODAL. Outside the region sit ideas that shape agent behaviour across calls, exploit billing mechanics (cache TTLs, wall-clock), or gate the harness's own injections rather than the model's.

## Convergence & Disagreement
- Review Lanes: miner (lead) + tails (Delta Re-review) + folk (Review Acuity Label) + alien (Green Lane Customs, the 1-in-20 audit).
- Verbatim-or-Vault: miner (lead) + folk (Minutes, Not Transcript) + alien (The Weighbridge) + alien (Partial Discharge).
- Spawn Tax: miner (lead) + folk (Dispatch Ticket) + alien (Feeder or Mainline).
- Salvage List: miner + tails (Live-Order Compactor).
- Skill Roster Diet: miner + folk (The 86 Board).
- Disagreement: the four-generator convergence on Skill Roster Diet and its 6-1-0 duel record were both wrong on the facts; the harness already ships the tool. Convergence measures how obvious an idea is, not whether it is still open.

## Validate Next
- Review Lanes: dry-run the lane picker over the last 30 merged VistaMobileBE PRs and compare to which review actually ran and which produced SUPPORTED findings. Zero misses on money paths is the bar before any skip acts.
- Cache Warm-Keeper: one script over last month's transcripts: list every `cache_creation_input_tokens` spike over 100k, the Bash command before it, and its duration. If fewer than 20% of spikes follow a backgroundable command, the PreToolUse half is not worth building.

## Final Cut Is Yours
This ranking is a funnel, not a verdict. In the only RCT that built ideas out (~100 expert-hours each), LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment — especially between the barbell's two ends.

---

Follow-on pipeline for any pick: `idea-autopsy:iterate-to-v2` → `product-management:write-spec` / `to-prd` → `idea-autopsy:evaluate-proposal-harsh`.

Working files (briefs, raw generator outputs, rankings, demand-checks): `/tmp/claude-1000/-home-alex/5a45d929-3e13-4fbd-a79d-240ac78da8ec/scratchpad/nebula/`
