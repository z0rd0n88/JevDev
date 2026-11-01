# vista-dw-review: PR #1063

**Reviewed:** `docs/975-spec-q8-addendum` at `e7199bf4`, against `main` (`3373e8bc`).
**Verdict: APPROVE.** Two LOW wording findings, both fixed in `64b36562`.

## Findings (both LOW, fixed in `64b36562`)

| # | Finding | Fix |
|---|---|---|
| L1 | "The fixed disclaimer and the result record" are terms the spec never defines: they come from the implementation plan ("Evidence and report", Task 4). | The sentence points at the plan's section and task. |
| L2 | "The owner approved this addendum" is ambiguous: the spec uses "owner" for the implementation owner and for the scope owner. | Names `perseus08`, as the plan's Task 6 Step 2 does. |

## Refuted

- "`DRY_RUN_GATE_EVAL` does not exist" despite `SigningAuditRows.dryRunGateEval`: that is a builder function, not an event type; the claim is scoped to `AuditEventType`, which has no such value.
- "A dry-run signature writes a `LIVE_SUBMIT_GATE_EVAL` row" is incomplete: a ledger write failure leaves a forensic `SIGNING_FAILURE` row instead, but the sentence states the normal outcome, as the pipeline's own KDoc does, and "never `SIGNING_SUCCESS`" holds on every path.
- Appending conflicts with `docs/AGENTS.md`: that rule is about superseding a whole dated file without renaming it; this is a narrow correction that keeps the file and its approved text.
- Something else on `main` still treats `DRY_RUN_GATE_EVAL` as real: outside `docs/reviews` and `docs/superpowers` (records), the only hits are the three spec lines the addendum corrects.

## Checked and correct

`DRY_RUN_GATE_EVAL` appears in the spec exactly at SMK-R05, SMK-R07 and the MSH-02 row. `AuditEventType` (`DelegatedExecutionAuditRecord.kt:32`) has `LIVE_SUBMIT_GATE_EVAL` and no `DRY_RUN_GATE_EVAL`; the closed-gate path writes `LIVE_SUBMIT_GATE_EVAL` (`SigningAuditRows.kt:135`), the open-gate path `SIGNING_SUCCESS`. The linked #975 comment records the Q8 decision. The PR description's claims hold, including the plan's Task 6 Step 2. `check-docs-hygiene.py` is clean at both commits; CI Docs hygiene passed on `e7199bf4`.
