# Coding standards

Read during review. Anything a check can enforce belongs in `check.sh`, not here.

## Secret redaction

Secret patterns live only in `redaction.py`; `tests/test_redaction.py` holds the contract table and fails on a second redactor.

- **Pick the view by what reads the text.** A scope judge reads `redact()`, so a value stops before the next statement. Text read only for its content uses `redact_strict()`, which fails closed.
- **Fix over-redaction only when the must-hide rows still pass.** A name lost from a report costs little, and a leaked secret costs a rotation. Add the leak and the survivor to the table in the same change.
- **State goes to Jev through `jev_patterns.call()`, which redacts it.** `redacted=True` needs a reason in the test's `opt_outs`.
- **Any change to `SECRETS` bumps `SENTINEL_VERSION`.**
