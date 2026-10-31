# New Jev features for the Claude Code, Codex and agy workflow

**Date:** 2026-10-31

**Status:** Brainstorm output backed by live demand checks. Nothing here is built, calibrated or validated in production. It builds on the 2026-09-27 [`jev-idea-nebula.md`](jev-idea-nebula.md) and [`jev-feature-opportunities.md`](jev-feature-opportunities.md), which were written before the installed gates and the shadow log existed.

## How to read this

We ran the Idea Nebula process four times in parallel, once each for code quality, security, speed and token cost. Each run used four independent idea generators, one ranker that never saw who wrote what, and live web checks on the top five finalists. The input was 30 days of transcripts (1,114 sessions, 15,530 Bash calls, 781 subagent spawns), the 30k-row Jev shadow log, and the git history of 12 repos. In total that gave 92 ideas, 32 finalists and 20 demand checks.

Terms used below:

- Shadow mode: the hook logs what it would have done and changes nothing.
- Gap score: how bad the pain is (1 to 5) times how many existing products fail at it. Higher means a bigger opening.
- Verdicts: GROUNDED means enough independent complaints and a real opening. WEAK means the pain is real but little is missing from the market. DOWNGRADE means too few complaints or no paying vendor. KILL-ZONE means a free tool, or one line in CLAUDE.md, already covers 80% or more of it.
- UNVERIFIED means the idea was a finalist but not among the five checked in its run.
- Duel record: wins, draws and losses from the ranker's pairwise duels. Every pair was judged in both orders, and only a verdict that survived the swap counts as a win. A record of 5-2-0 means five wins, two draws, no losses.
- MAD: median absolute deviation, a robust measure of how far a value sits from the typical one.
- RCT: randomized controlled trial.

## What to build first

Five ideas turned up in more than one run. That is the strongest signal here.

1. Review triage inside the loop. Finding Triage and Convergence (speed) and Review Lanes with Re-Review Skip (tokens) are both GROUNDED, with gaps of 24 and 20. Jev grades findings and picks reviewer lanes so the review, fix, re-review loop stops paying for a full panel every round. This is the best-evidenced build.
2. Spawn gating on the Agent call. Spawn Dispatcher (speed) and Spawn Tax (tokens) are the same idea. GROUNDED, gap 16, 42 complainants. Jev prices a subagent before it runs, then rewrites its model and effort or refuses it.
3. Undo instead of block, plus watching the retry. Dead-Man's Stash (gap 25) and Second Try (gap 16), both GROUNDED. Snapshot before a destructive command, then judge what the agent does after any block.
4. Keep secrets out of the transcript. Redact-at-Source, GROUNDED, gap 20. Rewrite the command so the value never prints.
5. Narrow output per situation. Verbatim-or-Vault, GROUNDED, gap 16. This is the judgment that rtk and context-mode lack.

Two popular finalists died on evidence. Fire the Allowlist is obsolete because Anthropic shipped compound-command splitting in August 2026. Skill Roster Diet is a KILL-ZONE because `/skill-doctor` is built in.

---

# Run 1: code quality

4 generators produced 23 ideas, 8 became finalists, and 5 got a live demand check. The best safe pick is Stowaway Hunks: GROUNDED, gap 24, and six shipped tools all check file paths while none scores hunks against the request. The most interesting moonshot is Mutant Oracle, which uses Jev to predict mutation-test kills and runs real pitest only on the predicted survivors. It lost every duel on plausibility and stays for its distance from the obvious.

## Safe picks

1. **Stowaway Hunks.** A Stop hook scores every hunk in the working diff for "does this trace back to the request", names the stowaways, and can move them into a separate patch. Duel record 2-2-3. It goes one step past the "unrequested-change detector" trope by tracing each hunk and quarantining it with `git apply -R`. Stop hooks now carry `transcript_path` and can block with a reason. Start from the compaction advisor's Stop scaffolding and plain diff parsing, in shadow mode writing `stowaways.jsonl`. The risk is that a request that changes over several turns makes honest hunks score low. Demand: GROUNDED, gap 24, about 30 complainants ("who told you to do that?"), six vendors that all rely on path allowlists.
2. **Code Passport.** Keep a rolling baseline (median and MAD) per repo of test strength, suppression rate, prime-directive breaches and slop density for every edit, and flag drift from the repo's own normal. Duel record 5-2-0. It replaces the single fixed bar that every other idea uses. Scoring every edit is free at Jev prices, and PostToolUse hands the hook the old and new strings directly. One PostToolUse hook writing `passport.jsonl` is enough, and VistaMobileBE builds a baseline in a week. The risk is that a slop-prone baseline makes slop look normal, so it needs a hard floor on suppressions. Demand: GROUNDED, gap 20, 24 complainants. Evolution Engine works per commit, sentrux checks structure only, and constraint-driven-development is prose.
3. **Stub Smuggler Alarm.** Detect "compile error, then a hardcoded mock or fallback in production code" and deny the edit until the agent reads the type it was fighting. Duel record 5-1-1. It judges a two-turn pattern, not one hunk. PreToolUse can deny with a reason, and the Kotlin and TypeScript compilers name the exact symbol. It needs one extra state field and two questions on the write gate. The risk is that DI test doubles and feature flags look identical. Demand: GROUNDED, gap 16, 28 complainants. One correction from the check: PreToolUse does not receive the previous tool result, so a PostToolUse companion has to cache the last failed Bash result to disk.
4. **Alibi Check for "pre-existing".** When the agent calls a failure pre-existing or flaky, Jev scores whether the session's diff could have caused it, and the stop is blocked until a base-branch run is shown. Duel record 5-2-0, the winner. It targets the one sentence where bugs get waved through. Worktree-per-session makes the base comparison one command. Start with failure-signature regexes for Gradle, pytest and flutter, in shadow mode against last month's roughly 15 "pre-existing" claims. The risk is that flaky suites make the comparison flaky. Demand: WEAK, gap 16. About 20 complainants, no paid vendor, and free regex Stop hooks already ban the phrase. Jev's only real contribution is the causal scoring that avoids false alarms. Compare against a worktree, not `git stash`, because stash drops are a documented way for agents to lose work.
5. **Receipt or It Didn't Happen.** Four of the four generators proposed it. A Stop hook refuses to end a turn on "tests pass" unless the transcript holds a command that could have produced that result, and it stamps a claim, command, exit-code table into the PR body. Duel record 1-3-3. This sits inside the obvious region, so the receipt table and SubagentStop coverage are the only non-obvious parts. Stop can block with a reason, and METR measured reward hacking in about 30% of agent runs. The transcript parser already exists, so an afternoon with an offline test over 20 hand-labelled turns is enough to start. The risk is that tests run inside subagents or Workflow steps never show up in the parent transcript. Demand: UNVERIFIED.

## Moonshots

These are high-variance bets kept because they are far from the obvious. Expect most to die under validation.

1. **Lookback Retesting.** Treat every `fix:` commit as a labelled bug. Re-score the diff that introduced it with every current Jev question, and report recall per question. Duel record 1-4-2. It judges the judge. Re-scoring every old diff on every question revision costs cents. Start with a CLI next to `ask_jev_files.py` on VistaMobileBE's 29 fixes. The risk is noisy labels. Demand: DOWNGRADE, gap 12, with only 4 direct complainants. Greptile and Tenki publish replay benchmarks that favour themselves, and nobody sells per-repo replay. The idea that AI commits are conventional-commit tagged only holds where CLAUDE.md enforces it.
2. **Pre-Filed Exemptions.** The agent may break a guarded rule only by filing a justification first, and Jev checks that the filing covers the actual act. Duel record 1-2-4. The risk is that the agent files an exemption as step one of every task. Demand: UNVERIFIED.
3. **Mutant Oracle.** Generate trivial mutants by text substitution, ask Jev which ones the test file would catch, run real pitest only on the predicted survivors, and flag tests that catch nothing. Duel record 0-0-7. It scores what a test would catch, not the test. The risk is that this is simulation, and nobody would recheck the calibration. Demand: UNVERIFIED.

## Demand evidence

| Idea | Independent complaints | Existing paid vendors | Gap | Verdict |
|---|---|---|---|---|
| Stowaway Hunks | About 30. "The agent routinely touches unrelated files, removes comments, fixes unrelated TypeScript errors, and applies formatting changes that were never requested." (Cursor forum 165633). "Claude Code does more than I asked" (claude-code#89579). | Cursor review, CodeRabbit out-of-scope check, scopediff, guard-dog, over_reach_detector | 4×6=24 | GROUNDED |
| Code Passport | 24. "If the same agent writes the tests and the code, it will happily weaken an assertion, add a skip" (HN 50149155). Also claude-code#319 and #45550. | Evolution Engine, sentrux, drift-analyzer, constraint-driven-development, PR bots | 4×5=20 | GROUNDED |
| Stub Smuggler | 28. "Claude cheats constantly at the tests ime. It frequently tests the mock instead of the UUT" (HN 45519398). Also claude-code#2345 and #6984. | agent-guard-hooks (tests only), output-validator (warns only), CLAUDE.md prose | 4×4=16 | GROUNDED, but PreToolUse lacks the prior tool result |
| Alibi Check | About 20. "calmly resolves it with a declaration that it was a 'pre-existing failure'" (HN 47866414). claude-code#59293 was closed NOT_PLANNED. | None paid. Free regex hooks stop-phrase-guard and no-vibes, and a prove-pre-existing skill. | 4×4=16 | WEAK |
| Lookback Retesting | 4 direct, 35 adjacent on review-gate noise | Greptile, Tenki and Entelligence benchmarks, run by the vendors | 3×4=12 | DOWNGRADE |
| Receipt, Pre-Filed Exemptions, Mutant Oracle | Not checked | | | UNVERIFIED |

## Modal region: what we refused to rank as novel

Any single-pass brainstorm on "LLM-judge for AI-coding quality" lands on the same six tropes: a per-edit linter-with-a-model that scores the diff for bugs and style, an end-of-turn verifier that checks "tests pass" against the transcript, a rule-compliance checker that re-injects or grades CLAUDE.md/AGENTS.md adherence, a test-quality scorer that flags tautological or mocked tests, a PR triage router that picks review depth, and a quality dashboard of those numbers. Everything in that region is a judgment applied to one artifact at one fixed moment against one fixed bar.

## Where generators agreed and disagreed

- Receipt or It Didn't Happen came from the miner as the lead, plus Entourage Liability (alien), Polygraph at Stop (tails) and Claim Ledger at Stop (folk).
- Stowaway Hunks came from tails at the Stop seam and folk as a pre-commit check.
- Test bending at write time came from folk (Fitted-Assertion Gate) and the miner (Assertion Worth Ledger). The ranker pruned both as dominated by Stub Smuggler.
- The ranker put Alibi Check first, but the demand check downgraded it to WEAK because free regex hooks already own the blocking half. The Receipt idea, at 1-3-3, is what four generators and the complaint corpus actually want.

## Validate next

- Stowaway Hunks: run one week of shadow `stowaways.jsonl` on VistaMobileBE sessions. Count stowaway hunks per PR and hand-label 30 of them. Act only if precision is above 0.8.
- Mutant Oracle: run the predictor on 5 Kotest files, then run real pitest once on the same files and compare predicted to actual kills. Drop it if agreement is under 0.7.

## Final cut is yours

This ranking is a funnel, not a verdict. In the only RCT that built ideas out, at about 100 expert-hours each, LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment, especially between the two ends of the barbell.

---

# Run 2: security

4 generators produced 24 ideas, 8 became finalists, and 5 got a live demand check. The best safe pick is Redact-at-Source: GROUNDED, gap 20, about 38 complainants, and five vendor classes that all miss the point before a command runs. The most interesting moonshot is Second Try, GROUNDED at gap 16, which judges the retry after a block. Nothing logs that turn today. Dead-Man's Stash won the most duels, but two open-source hooks already snapshot before destructive commands, so its defensible slice is narrow.

## Safe picks

1. **Dead-Man's Stash.** Merged with Snapshot Before Strike, which another generator proposed independently. It never blocks a destructive git or rm command. Jev asks whether the command would discard work nothing else holds, a hidden ref snapshots the tree, the command runs, and `jev-undo` restores. Duel record 6-1-0. It makes the irreversible undoable instead of blocking it. PreToolUse can snapshot and soften in one pass, and the sentinel log has 221 irreversible rows to backtest against. It needs one hook and one CLI subcommand. The risk is that `git stash create` misses untracked files, and a half snapshot is worse than none. Demand: GROUNDED, gap 25, with a warning. claude-oops and git-safepoint already snapshot on PreToolUse using regex lists, so Jev's slice is the unheld-work judgment and the regex-miss gap in claude-code#97881.
2. **Hemovigilance Register.** A weekly CLI checks every shadow `would_block` row against what happened next, computes precision per block-reason template, and flips a gate from shadow to act, one template at a time, only above 0.9. Duel record 5-2-0. It decides how shadow mode ends. About 1,400 would_block verdicts exist and nobody has read one. Start with the adjudication pass alone and no `act.json`. The risk is that "what happened next" is weak ground truth. Demand: DOWNGRADE, gap 9. Only 5 direct complainants ("A 90% accurate guardrail is a user-blocking machine"), shadow modes exist at several vendors but none promotes on measured precision, and no budget line exists.
3. **Redact-at-Source.** Before a Bash command runs, Jev judges whether its output will print credentials, and the hook rewrites the command through `updatedInput` so the values are masked before they enter the transcript. A taint ledger records which session files would have held which key names. Duel record 5-1-1. `updatedInput` is live, and transcripts and file-history became a new leak surface in the last 18 months. The environment-facts rule already does this by hand with `sed 's/=.*/=<set>/'`. The risk is that over-masking breaks JWT debugging. Demand: GROUNDED, gap 20, about 38 complainants, including "I still had 600 secrets in plaintext", and claude-code#63593 was closed without a fix.
4. **Cash Cage.** An Edit hook on money paths classifies each hunk by direction of funds. Only hunks that move money out of user custody need a human confirmation, and float in money math is blocked. Duel record 3-1-3. Withdrawals and the MoonPay on-ramp shipped this quarter. Start with an `ask_jev_files.py hunks` subcommand tested on the withdrawal retro's own diff. The risk is confirmation fatigue. Demand: DOWNGRADE, gap 8. There are 8 complainants, and every loss with a URL happened when a transfer ran, not when code was edited. The check recommends moving the gate to a PreToolUse Bash check on outgoing transfers, which is what claude-code#21774 asked for, and folding the float ban into `audit-numeric-types`.

## Moonshots

These are high-variance bets kept because they are far from the obvious. Expect most to die under validation.

1. **Second Try.** The hook fires only when the previous command was blocked. Jev asks whether the new command is the same action reworded to dodge the guard. Evasions are hard-blocked and logged. Duel record 3-1-3. The `PermissionDenied` hook with `retry` landed in v2.1.88, and Backslash measured 8 of 8 denials being rerouted. Start with a per-session state file and three recorded block and retry pairs. The risk is that most retries are legitimate. Demand: GROUNDED, gap 16, 27 complainants, including "the Bash tool with tee would achieve the same file write while bypassing the hook entirely". Design caveat: `PermissionDenied` does not fire for PreToolUse or deny-rule blocks, so the hook has to record its own blocks, and a Bash to Write reroute also needs the hook on Write and Edit.
2. **Silhouette.** Replace high-entropy tokens with shape descriptors such as `<HEX:64>` and `<JWT 3-part>` inside `jev_patterns.call` before anything reaches OpenRouter, then gate pastes, writes and commits on the shape. Duel record 1-1-5. It fixes a leak in the existing gate instead of adding another gate. The risk is that a fixture's fake 64-char hex and a real private key look identical. Demand: UNVERIFIED.
3. **Say-Do.** Read the assistant's last narration and ask whether the command does what the sentence says. Duel record 0-2-5. It catches hallucinated and injected actions as a mismatch. The risk is that terse narration gives it nothing to compare. Demand: UNVERIFIED.
4. **Who Told You That.** Tag imperative text in pastes and fetched pages, then at Stop attribute each write, commit and push to the user, a paste, a page or a PR comment. Duel record 0-1-6. It audits obedience instead of blocking on the way in. The risk is noisy attribution. Demand: UNVERIFIED.

## Demand evidence

| Idea | Independent complaints | Existing paid vendors | Gap | Verdict |
|---|---|---|---|---|
| Dead-Man's Stash | 34. "ran `git reset --hard origin/main` autonomously within the first second of session startup on **two separate occasions**" (claude-code#34327). | /rewind (ignores Bash), the auto-mode classifier, Cursor checkpoints, claude-oops, git-safepoint, Unfucked | 5×5=25 | GROUNDED, narrow gap |
| Redact-at-Source | About 38. "records tool stdout **verbatim**... durably on disk in the session transcript with no built-in redaction" (claude-code#63593). | Anthropic's shared-only redaction, PostToolUse scrubbers, Sieve-style scanners, vault brokers, Cursor ignore | 4×5=20 | GROUNDED |
| Second Try | 27. "Nine times the same change reached the disk seconds later by another route" (Backslash). | Anthropic's denial valve, the regex guard family, Codex and Cursor allowlists, rtk | 4×4=16 | GROUNDED |
| Hemovigilance Register | 5 direct. "deployed a guardrail that flagged 30% of legitimate interactions and the teams started routing around it" (r/LLMDevs). | Shadow modes in OrcaRouter, Strands and Writer, none with promotion | 3×3=9 | DOWNGRADE |
| Cash Cage | 8. "sent 3.086 SOL (~$357 USD) to an incorrect wallet address... The difference between the addresses is a missing 'u' character" (claude-code#21774). | Coinbase Agentic Wallets and Circle policies at runtime, plus path-based edit hooks | 4×2=8 | DOWNGRADE, aim at runtime |
| Silhouette, Say-Do, Who Told You That | Not checked | | | UNVERIFIED |

## Modal region: what we refused to rank as novel

A generic single-pass brainstorm on "LLM judge for agent security" lands on five tropes: a secret-pattern scanner on writes/commits/outputs, a dangerous-command blocklist on PreToolUse (`rm -rf`, `git reset --hard`), an "ignore previous instructions" detector on fetched/tool output that flags or denies, a dependency-install vetting check (age, downloads, typosquat distance), and a money-code linter that greps for floats in amount math. All of them block on the way in, judge each event in isolation, and treat the repo or the command as the thing to protect rather than the transcript, the retry, the narration, or the shadow log itself.

## Where generators agreed and disagreed

- Dead-Man's Stash came from the miner and folk (Snapshot Before Strike).
- The install gate came from the miner (Install Bouncer) and folk (Lookalike). The ranker pruned it as obvious.
- The money-path edit gate came from alien (Special Requirements Flag) and the miner (Lot-Size Lie Detector). Cash Cage was kept, then downgraded.
- Injection tainting came from three generators: folk (Taint Window), the miner (Taint Trail) and alien (Irradiated Output). The ranker pruned it as obvious in favour of Say-Do and Who Told You That.
- Leak Ledger (tails) and Lookback (alien) overlapped. Silhouette replaced them.
- The ranker's second safe pick, Hemovigilance, is the one the market has no budget for. Its fifth-place moonshot, Second Try, is better grounded than two of the safe picks.

## Validate next

- Redact-at-Source: replay the 30,458 sentinel commands offline, count `would_rewrite`, and hand-check 50 rewrites for over-masking. Ship in shadow if under 5% of rewrites would have hidden something the agent needed.
- Second Try: pull every block and retry pair from last month's transcripts, about 195 guard blocks plus 94 classifier denials, and label 40 by hand as evasion or genuine fix. Act only if Jev agrees with the labels above 0.85.

## Final cut is yours

This ranking is a funnel, not a verdict. In the only RCT that built ideas out, at about 100 expert-hours each, LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment, especially between the two ends of the barbell.

---

# Run 3: speed

4 generators produced 23 ideas, 8 became finalists, and 5 got a live demand check. The best safe pick is Finding Triage and Convergence: GROUNDED, gap 24, three generators proposed it independently, and six vendors fail at per-finding provenance. The most interesting moonshot is Sealed Baton, which stamps handoff notes with per-claim seals tied to file hashes. It is the furthest from the obvious and lost every duel. The duel winner Fire the Allowlist was downgraded because Anthropic shipped compound-command splitting in August 2026 and the pain that remains is a different problem.

## Safe picks

1. **Finding Triage and Convergence.** Three generators proposed it. Before each re-review round, Jev grades every finding: introduced by this diff (via blame), duplicate of a prior round, severity, and whether the fix is mechanical. It picks the one keystone finding, skips the reviewer fan-out for mechanical fixes, and stops the loop at zero new HIGH findings. It reorders and labels, and never deletes. Duel record 5-2-0. It scores novelty across rounds, so the stop condition becomes "converged" instead of "clean". Looping is the default in multi-agent-review 2.0. Start with a `findings` subcommand run over the last 10 saved reviews in `docs/reviews/`. The risk is that a restated finding is sometimes the signal that the fix was wrong. Demand: GROUNDED, gap 24, 27 complainants. One practitioner running the same kind of loop names "False convergence" outright.
2. **Hook Appeals Court.** Three generators proposed it. Before a regex guard returns exit 2, it asks Jev for a 300 ms second opinion. Overturned blocks are logged, and a weekly job proposes a narrower regex. secrets-guard may only downgrade to a warning, and all three generators excluded it from silent pass-through. Duel record 5-2-0. It aims to retire the regex, not add another gate. The auto-mode prompt now pushes cat, sed and heredocs, so guards written for clean commands misfire more. Wrap `merge-guard.py`'s block path first, in shadow mode against its 54 logged blocks. The risk is that a 0.35 threshold on secrets-guard is a rotation incident. Demand: GROUNDED, gap 16, 32 complainants, with two cuts. About 75% of the loud complaints are about Anthropic's built-in worktree guard, which runs after hooks and cannot be appealed. And the most-upvoted ask wants fewer LLM judgments in the hook path.
3. **Déjà-Vu Guard.** File every subagent report and every completed irreversible command. After compaction, or on any new spawn, Jev checks whether the proposed action duplicates filed work, with "files changed since the report" in the state, and hands back the stored result. Duel record 4-0-3. It acts after compaction on what not to redo. SessionStart(compact) and PostToolUse on Agent now exist as hook points, and you run about 781 spawns a month. Start with a PostToolUse Agent filer and a replay over the 58 compaction boundaries. The risk is that a legitimate re-run is blocked as a duplicate. Demand: GROUNDED, gap 16, 33 complainants ("The backend review agent's results were lost during context compaction. Let me re-run it"). The root cause is a harness bug Anthropic could close any week, and open bug #91910 makes SessionStart(compact) misfire inside subagents.
4. **Spawn Dispatcher.** Two generators proposed it. PreToolUse on Agent scores difficulty on a 4-rung rubric, refuses spawns a Grep would answer, and rewrites model and effort for mechanical work. Duel record 1-2-4. It is squarely in the obvious region except for the "don't spawn, Grep instead" veto. Agent takes `model` and `effort` per call, and there is a roughly 10x price spread between tiers. Start by replaying the 781 prompts and comparing predicted class to actual spend. The risk is that a downgraded builder ships worse code. Demand: GROUNDED, gap 16, about 42 complainants ("launched 7 sub agents which burned through my budget"). Cut the Skill-sibling veto, since no one complained about it. Also watch #100701, where `effort` is dropped for named in-process teammates.
5. **Fire the Allowlist.** Merged with Green Lane. A PermissionRequest hook splits compound commands, scores each segment, and auto-allows segments that are read-only or reversible and covered, using earned per-repo, per-command-family trust lanes. Duel record 5-2-0, the winner. It is obvious at its core. Claude Code now has a PermissionRequest hook event, and the shadow log supplies 30k labelled rows to set thresholds from. Start with a shadow hook replayed against `sentinel.jsonl`. The risk is that one false allow on an irreversible command outweighs a thousand saved prompts. Demand: DOWNGRADE, gap 9. claude-code#16561 closed as completed on 2026-08-17 with native splitting on `&&`, `;` and `|`, free native auto mode covers most users, and the one issue asking for exactly this (codex#50572) drew zero votes. What remains is people who reject auto mode on principle, and agy, which has no auto mode.

## Moonshots

These are high-variance bets kept because they are far from the obvious. Expect most to die under validation.

1. **Fairway Pilot.** A PostToolUse hook reads the last 15 calls and asks Jev which phase the session is in. On a phase change it injects the mandatory next move: the review skill, merge cleanup, worktree teardown, or the matching gotcha paragraph after a guard block. Duel record 1-2-4. It routes on position, not on the prompt. The risk is nagging, so the cooldown and confidence floor are the whole product. Demand: UNVERIFIED.
2. **Short-Landed Report.** A SubagentStop hook asks whether the report answers the brief and whether the gap is one SendMessage away. It then routes to a continuation instead of a respawn, with a brief-completeness check before dispatch. Duel record 0-3-4. The risk is that the hook may fire on the spawn acknowledgement, not the result. Demand: UNVERIFIED.
3. **Sealed Baton.** `ask_jev_files.py seal baton.md` stamps each supported claim with a seal tied to file hashes. The receiving session re-hashes and injects "sealed, do not re-read" or "unsealed, verify first". Duel record 0-1-6. The reader side makes no Jev call. The risk is that a claim naming no file can never be sealed. Demand: UNVERIFIED.

## Demand evidence

| Idea | Independent complaints | Existing paid vendors | Gap | Verdict |
|---|---|---|---|---|
| Finding Triage | 27. "I specifically instructed it to ignore nitpicks, but it still added such comments." (HN 42484498). "False convergence" (Vaughan). | CodeRabbit, Greptile, Copilot review (auto-resolve since Sept 2026), Bugbot, Claude Code Review, open-source loops | 4×6=24 | GROUNDED |
| Hook Appeals Court | At least 32. "`grep -n 'git-commit-id' …` is refused: the quoted grep pattern is treated as a git invocation" (claude-code#100806). | Anthropic classifier and worktree guard, ccgate, cc-safety-net, cc-safe-setup, secret scanners | 4×4=16 | GROUNDED, built-in guard unreachable |
| Déjà-Vu Guard | 33. "It re-runs the full test suite even when... No code changes occurred between the test run and the repeated run" (claude-code#27648). | Anthropic PostCompact, claude-mem, Cozempic, Codex (open #29356) | 4×4=16 | GROUNDED, vendor may fix it |
| Spawn Dispatcher | About 42. "All 46 subagents ran on Opus … no automatic downgrade of sweep/verification subagents to cheaper models." (claude-code#66023). | Anthropic's static per-agent model and effort, workweave router, Rayline, nedjamez hook | 4×4=16 | GROUNDED, cut the skill veto |
| Fire the Allowlist | About 35, mostly before August 2026. "I had to babysit it for hours today because it insisted on prefixing every command with `cd blah &&`" (claude-code#16561, now closed). | Anthropic native splitting and auto mode, Codex execpolicy, mutgarth/automode | 3×3=9 | DOWNGRADE |
| Fairway Pilot, Short-Landed Report, Sealed Baton | Not checked | | | UNVERIFIED |

## Modal region: what we refused to rank as novel

The obvious single-pass brainstorm on "Jev for faster Claude Code" is gate-wrapping: put one noul in front of each existing yes/no gate (permission prompt, regex guard, subagent spawn, AskUserQuestion, review-finding severity, "is the agent looping") and threshold it, with a shadow log first. Its tropes are the auto-approve classifier that replaces the allowlist, the model/effort router at the Agent call, the "answer the question yourself" gate, the thrash detector, and the finding-severity triage. Anything whose whole contribution is "same gate, now a probability instead of a regex" sits inside it.

## Where generators agreed and disagreed

- Hook Appeals Court came from the miner, plus folk (Manager Override Code) and tails (Guard Appeals Court).
- Finding Triage came from the miner, plus tails (Review-Loop Terminator, which added the keystone pick) and folk (Auto-Pay Findings).
- Spawn routing came from the miner (Spawn Dispatcher) and folk (Green Lane for Spawns).
- Allowlist replacement came from the miner (Fire the Allowlist) and alien (Green Lane).
- Self-answering questions came from the miner and tails (Default-It Stop Gate). The ranker pruned it.
- Churn detection came from tails (Fresh-Eyes Ejection Seat) and folk (Three-PIN Lockout). The ranker pruned both in favour of Fairway Pilot.
- The miner's reason for Fire the Allowlist ("among the most-upvoted open issues") was wrong. The issue closed two months before the run.

## Validate next

- Finding Triage: run the `findings` subcommand over the last 10 saved review reports and join the results to finding-fixer's SUPPORTED and REFUTED verdicts. Report the precision of the "duplicate" and "pre-existing" labels, and act only if both are above 0.85.
- Sealed Baton: seal the next 5 batons by hand with the subcommand and count how many seals are still intact when the receiving session opens them. If under half survive, rethink the file-hash keying before writing any hook.

## Final cut is yours

This ranking is a funnel, not a verdict. In the only RCT that built ideas out, at about 100 expert-hours each, LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment, especially between the two ends of the barbell.

---

# Run 4: token cost

4 generators produced 22 ideas, 8 became finalists, and 5 got a live demand check. The best safe pick is Review Lanes with Re-Review Skip: GROUNDED, gap 20, with "$15-25 per PR" threads at 285 points, five vendors that bill per run, and none that route by risk. The most interesting moonshot is Cache Warm-Keeper: GROUNDED, gap 16, and the best duel record in the pool. It sits in the moonshots because it bets on billing mechanics, not on shrinking context. The duel winner Skill Roster Diet is a KILL-ZONE, since `/skill-doctor` ships in the harness.

## Safe picks

1. **Review Lanes with Re-Review Skip.** Four generators proposed it. Pre-push and the first step of the review skills have Jev score diff risk and pick lanes: none, standards, correctness and tests, security and money, or the full panel. Money and auth paths always force the security lane. After a fix round, a "fix stayed within the findings" answer sends one verifier instead of a full re-review. A random 1-in-20 full audit of skipped PRs keeps the classifier honest. Duel record 2-3-2. The random audit lifts it out of the "lighter review" trope. Per-push looping review became the billing unit in 2026. Start with a dry-run CLI over the last 30 merged PRs, compared to what actually ran. The risk is skipping a lane on a diff that quietly touched a money path. Demand: GROUNDED, gap 20, about 23 complainants ("$75-250/day, potentially $1500-5000/month just for reviews").
2. **Verbatim-or-Vault.** Four generators proposed it. PreToolUse on Bash and whole-file Reads asks Jev, per situation, whether the agent needs the output verbatim, only a derived answer, or already has it. Large derive-only output goes to a scratch file with a summary line. Reads are narrowed to the section Jev picks. Failure output always passes through verbatim. Files already read are refused, with the turn and line range they were read at. Duel record 2-3-2. It decides per situation, not per command type. `updatedInput` makes the rewrite possible without a proxy binary, and rtk proved both the saving and the failure mode. Start by adding three questions to the existing bash gate and replaying 30k rows. The risk is vaulting the one output the agent needed. Demand: GROUNDED, gap 16, about 24 complainants. rtk's top issue is "RTK Hook Increases Claude Code Costs by 18%", because compressed output made the agent write 50% more output tokens. The hook must say what it hid through `additionalContext`, or it repeats rtk's failure.
3. **Spawn Tax.** Three generators proposed it. PreToolUse on Agent prices each spawn: can the parent do it inline, which tier, how good is the brief, and will it re-read the parent's files. It then denies the spawn or rewrites model and effort. Duel record 0-2-5. `updatedInput` on Agent calls lets a hook rewrite the spawn, and per-subagent usage now lands in the local JSONL transcripts. Start with a replay script over your 781 real Agent prompts that prints the would-downgrade rate next to the tokens each spawn actually used. The risk is a wrongly downgraded builder. Demand: UNVERIFIED in this run, but the near-identical Spawn Dispatcher was checked in Run 3 and came back GROUNDED at gap 16.
4. **Salvage List.** Two generators proposed it. A PreCompact hook ranks which tool outputs and decisions must survive compaction under a hard token budget, writes `salvage.md`, and re-injects it at SessionStart(compact). It also adds a block of "standing orders", meaning user prompts that still bind. Duel record 0-1-6. It targets the one compaction channel that issue #89797 showed survives. PreCompact and SessionStart(compact) hook events now exist. Start by scoring one compacted session offline and comparing the result to what the agent re-read in the next 20 turns. The risk is that over-salvaging refills the context compaction just freed. Demand: UNVERIFIED.
5. **Skill Roster Diet.** Two generators proposed it. A nightly CLI scores every skill description against 30 days of prompts and proposes demotions, with tokens saved per turn. Duel record 6-1-0, the winner. Demand: KILL-ZONE, gap 6. `/skill-doctor` (v2.1.252 and later, and this machine runs 2.1.316) already reports per-skill cost, invocation count and last use. `skillOverrides: name-only` already drops the description according to current docs. codeprakhar25/optimize does the JSONL-grep proposal for free. The idea assumed `skillOverrides` keeps the description in the listing, and current docs contradict that, so re-check the same claim in your AGENTS.md. Do not build this. Run `/skill-doctor` instead.

## Moonshots

These are high-variance bets kept because they are far from the obvious. Expect most to die under validation.

1. **Cache Warm-Keeper.** PreToolUse backgrounds commands that Jev predicts will outlive the cache TTL, when the result is not needed before the next step. A Stop hook prints the computed rewrite cost when you look about to leave a large session. Duel record 6-1-0, the best in the pool. It moves work in time instead of shrinking anything. Main sessions now get a 1-hour cache and subagents a 5-minute one, and the `cache_creation` fields are in transcripts. Start by listing last month's cache rewrites over 100k tokens and joining each to the Bash command before it. The risk is backgrounding a command whose output the next step needs. Demand: GROUNDED, gap 16, at least 80 complainants ("Median Bash duration for those calls 600 s... 299 (about 92% of the rewritten tokens)", claude-code#99808). The Stop-hook half is crowded, with 10 or more keepalive repos. The defensible part is the PreToolUse backgrounding, which nobody ships. Past Bash durations in your own transcripts predict better than Jev does here.
2. **Injection Toll Booth.** A UserPromptSubmit wrapper runs your own injectors and drops the ones Jev says this prompt cannot use. Safety injections are never gated. Duel record 2-3-2. It gates what the harness prepends. The risk is suppressing the one injection the prompt needed. Demand: WEAK, gap 9. About 22 complainants on the general cache-read cost but only about 6 on injectors you own. The wrapper can touch only about 15% of the fixed overhead, and ai-nexus already sits on the same seam with GPT-4o-mini.
3. **LCL Consolidation.** After three orientation probes in a row (ls, cat, grep, git log) that Jev judges open-ended, block the fourth and ask for the rest as one script or one `ctx_batch_execute`. Duel record 1-4-2. It acts across calls instead of filtering bytes. The risk is that a wrong block adds a turn. Demand: UNVERIFIED. A cheap kill test: measure runs of consecutive read-only commands per session in `sentinel.jsonl`. If the median run is 2, drop it.

## Demand evidence

| Idea | Independent complaints | Existing paid vendors | Gap | Verdict |
|---|---|---|---|---|
| Review Lanes | About 23. "Two reviews totaled $214.43 — an average of $107/review" (claude-code#34114). "there is no way to unsubscribe… This creates runaway cost on active PRs" (#60723). | Anthropic Code Review, Copilot review, CodeRabbit, Greptile, Bugbot | 4×5=20 | GROUNDED |
| Verbatim-or-Vault | About 24. "RTK Hook Increases Claude Code Costs by 18%" (rtk#582). "repeated truncation and rereads are causing absurd context consumption" (codex#55684). | rtk, context-mode, Context Gateway, Claude Code's native truncation | 4×4=16 | GROUNDED |
| Cache Warm-Keeper | At least 80. "some sessions cost like 10x what they should because of cold caches" (HN 50238655). | Anthropic TTL settings and idle compaction, the keepalive plugin cluster, Codeman | 4×4=16 | GROUNDED |
| Injection Toll Booth | About 22 general, about 6 specific. "Cache reads as % of total: 99.93%" (claude-code#24147). | ai-nexus, unclog, Anthropic's manual controls | 3×3=9 | WEAK |
| Skill Roster Diet | About 30. "2,596 skills installed … 102,651 tokens loaded into every session" (r/ClaudeAI). | Anthropic `/skill-doctor` built in; skills-janitor, optimize, skill-graveyard | 3×2=6 | KILL-ZONE |
| Spawn Tax, Salvage List, LCL Consolidation | Not checked here. Spawn Tax's sibling was GROUNDED in Run 3. | | | UNVERIFIED |

## Modal region: what we refused to rank as novel

A generic single-pass brainstorm on "use a cheap classifier to cut agent token cost" produces five tropes: truncate or summarize tool output before it enters context (tail the build log, push it to a sandbox), gate or down-tier subagent spawns onto cheaper models, run a lighter review on low-risk diffs, prune the always-loaded prefix (unused skills, MCP tool descriptions), and make compaction keep the right things; plus the after-the-fact usage dashboard (ccusage, CodeBurn). Anything shaped "classify at an obvious choke point (Bash output, Agent call, review fan-out, prompt prefix, compaction), then shrink it" is MODAL. Outside the region sit ideas that shape agent behaviour across calls, exploit billing mechanics (cache TTLs, wall-clock), or gate the harness's own injections rather than the model's.

## Where generators agreed and disagreed

- Review Lanes came from the miner as the lead, plus tails (Delta Re-review), folk (Review Acuity Label) and alien (Green Lane Customs, which supplied the 1-in-20 audit).
- Verbatim-or-Vault came from the miner as the lead, plus folk (Minutes, Not Transcript) and two from alien (The Weighbridge and Partial Discharge).
- Spawn Tax came from the miner, folk (Dispatch Ticket) and alien (Feeder or Mainline).
- Salvage List came from the miner and tails (Live-Order Compactor).
- Skill Roster Diet came from the miner and folk (The 86 Board).
- Four generators converging on Skill Roster Diet, and its 6-1-0 record, were both wrong on the facts, because the harness already ships the tool. Convergence measures how obvious an idea is, not whether it is still open.

## Validate next

- Review Lanes: dry-run the lane picker over the last 30 merged VistaMobileBE PRs and compare to which review actually ran and which produced SUPPORTED findings. The bar before any skip acts is zero misses on money paths.
- Cache Warm-Keeper: write one script over last month's transcripts that lists every `cache_creation_input_tokens` spike over 100k, the Bash command before it, and that command's duration. If fewer than 20% of spikes follow a command that could have run in the background, the PreToolUse half is not worth building.

## Final cut is yours

This ranking is a funnel, not a verdict. In the only RCT that built ideas out, at about 100 expert-hours each, LLM pre-execution scores were weak-to-negative predictors of executed quality, and novelty advantages evaporated in execution. Pick with your own judgment, especially between the two ends of the barbell.

---

For any pick, the follow-on pipeline is `idea-autopsy:iterate-to-v2`, then `product-management:write-spec` or `to-prd`, then `idea-autopsy:evaluate-proposal-harsh`.
