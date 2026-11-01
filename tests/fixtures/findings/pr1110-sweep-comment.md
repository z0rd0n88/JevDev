## Review sweep 2026-10-30 (reviewed at `9be90f0a`)

One read-only `code-reviewer` lane on the PR's own diff against its base, then an adversarial pass that tried to refute every finding against the tree. Dispositions: **CONFIRMED** reproduced; **DEMOTED** real but over-rated (new severity shown); **REFUTED** could not be confirmed or outside this PR's delta. Record for all 16 open PRs: https://github.com/VistaMarkets/VistaMobileBE/blob/main/docs/reviews/2026-10-30-open-pr-sweep.md

**Reviewer verdict:** NEEDS-DISCUSSION. **After the adversarial pass:** NEEDS-DISCUSSION.

The reject() fallback is correct on double-write and consistency: both writes are CAS-guarded and ok flows from the fallback result. Three gaps: the new ERROR line passes the throwable, which can defeat its NFR-4 comment; the spec (FR-34, FR-23) is not amended to allow a REJECTED row with no SIGNING_FAILURE audit row; the fallback test does not pin the state-alone-evidence-logged contract. The other new tests would fail if their fixes were reverted, by reading only; no tests run.

### Findings that survived

- **LOW** (reviewer said MEDIUM) — Fallback ERROR line passes the throwable, so the NFR-4 claim in its comment is not guaranteed  [DEMOTED]
  - Where: Merchant/src/main/kotlin/com/vista/merchant/withdrawal/WithdrawalService.kt:1224-1231
  - Failure path: Placeholders are clean, but the trailing `e` is the audit-insert exception logged with message and stack. A Postgres CHECK/NOT NULL violation on delegated_execution_audit can carry 'Failing row contains (...)' with userId (DID), walletAddress and signedAmountDecimal, which NFR-4 forbids on one line. Driver rendering under the pinned versions not checked.
  - Fix: Log e.javaClass.name plus SQLState, or a redacted e.message, instead of the raw throwable; or add a log-capture assertion with an auditAppender that throws with row values. The existing `Failed to transition` line has the same exposure but is not new.
  - Evidence: WithdrawalService.kt:1224-1231 on refs/pr/1110; NFR-4 at spec:222; WithdrawalLogRedactionTest has no case for reject() with a failing append.
  - Skeptic: Mechanism real: Exposed 0.57's ExposedSQLException carries the PSQLException text and PgJDBC's logServerErrorDetail defaults to true, so a CHECK/NOT NULL violation carries 'Failing row contains (...)' (the repo says so itself in WalletDepositStore.kt:119). Demoted: the same shape already exists on main (:656 audit_attempt_failed logs the same exception; :1235 e2); only a constraint violation leaks, not an outage; signedDestination is null on the reject record so no full address; Exposed's own logger already WARNs the text; AC-6.12 has no failing-append case. Real hardening gap, repeat of an existing pattern.
- **LOW** (reviewer said MEDIUM) — Fallback deviates from FR-34 and FR-23, but the spec is not amended and the audit gap is permanent  [DEMOTED]
  - Where: docs/specs/2026-10-22-withdrawal-spec.md:125,153-154 vs WithdrawalService.kt:1221-1238
  - Failure path: After the fallback the row is REJECTED with no SIGNING_FAILURE row and nothing backfills one; the reconciler never revisits REJECTED. FR-23 says every post-admission refusal MUST be written to the audit; FR-34 says the failure row is appended before the rejection returns. For the post-SIGNING_SUCCESS case the chain ends in SIGNING_SUCCESS for a never-broadcast tx. The new marker withdrawal_reject_audit_unrecorded is not in FR-34's marker list. The PR edits only FR-26.
  - Fix: Amend FR-34 and FR-23 with the degraded rule; register the marker as an alert; decide whether a backfill sweep is needed or #1108 covers it.
  - Evidence: Spec lines 125, 153-154 unchanged; review record frames this as honouring FR-34, not amending it.
  - Skeptic: The spec conflicts with itself: FR-34 bullet 1 requires a SIGNING_FAILURE row for every REJECTED; bullet 2 requires a failed append to end REJECTED AUDIT_UNAVAILABLE logged at ERROR with the digest. When the audit store failed, both cannot hold; the fallback satisfies bullet 2 and logs digest and auditId; FR-35 already accepts PENDING when the REJECTED write fails. What holds: FR-34 untouched, the new marker in no spec list. Fix the spec text; no code change.
- **MEDIUM** — Fallback test does not pin the state-alone, evidence-logged contract  [CONFIRMED]
  - Where: Merchant/src/test/kotlin/com/vista/merchant/withdrawal/WithdrawalSigningFailureTest.kt:568-577, 593-609
  - Failure path: Asserts only 201, REJECTED, AUDIT_UNAVAILABLE. Does not assert the ERROR line, that no audit row exists for wd:<id>, or the 503 when the second write also fails. Dropping log.error leaves it green. The SIGNING_SUCCESS scenario does not route through the fallback.
  - Fix: Add log capture asserting one ERROR with the marker and withdrawalId; assert audit row count 0; add a case where store.transition also fails expecting 503.
  - Evidence: Test body on refs/pr/1110; PR body says the probe covered the three new pins, not this modified test.
  - Skeptic: AC-6.7 asserts only 201, REJECTED, AUDIT_UNAVAILABLE and callCount 0; no log capture, so deleting the log.error stays green, and the ERROR line is the only carrier of the audit evidence. Second-write-fails 503 untested. 'audit row count 0' adds nothing (rolls back by construction).
- **LOW** — Fallback loses the detailed audit reason from persistent state  [CONFIRMED]
  - Where: WithdrawalService.kt:1232-1238
  - Failure path: Normal path stores auditReason (e.g. NOTIFIER_NOT_READY:TIMEOUT) in the audit row; fallback persists only reject_reason, detail survives only in the log.
  - Fix: State it in the spec amendment.
  - Evidence: TransitionFields(rejectReason = reason) vs record.rejectOrFailReason.
  - Skeptic: Follows from there being no audit row; detail survives in the marker line. State it in the spec.

### Refuted by the adversarial pass

- ~~PR body claims narrower mutation coverage than the diff adds, and CI is unchecked~~ — Not a defect in the diff; the record says exactly what was probed; the modified AC-6.7 would also go red on the old code; follow-ups filed per the documented flow.

### PR hygiene
- Title/body match the diff: True. Test plan present: True. Issue link: Closes #1078, #1079, #1080, #1081.
- Unrelated changes: docs/guide/deployment.md owner-role note (from review finding 2) not in the body's bullets.
- 12 files match scope; no production default changed; FEE_UNAVAILABLE already in the internal OpenAPI 503 vocabulary; FR-34/FR-23 not updated for the fallback.

### Open questions for the author

- Is REJECTED-without-SIGNING_FAILURE an accepted FR-34 relaxation, and does #1108 cover a backfill?
- Should withdrawal_reject_audit_unrecorded join the alert list?
- Should the post-SIGNING_SUCCESS reject path also leave a CRITICAL line with the signature?

### Reviewer claims the skeptic re-checked

- None wrong. SMK-03 list has 14 vars after the drop and GatewayConfig.kt:27/:303 show GEOIP optional. WithdrawalRoutes.kt has exactly seven routes and the test lists seven.

### Not examined (residual risk)

- Whether Exposed/PG render row values in the audit-insert exception message
- Whether the WS change feed emits an update for a fallback REJECTED
- CI on the PR head; the author's test/stress/smoke claims not re-run
- Most of the review record; ARCH.md diff
- reject() on a row already advanced by the abandon sweep