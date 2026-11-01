"""The redaction contract: one table of what each view must hide and keep, and a guard against a second redactor."""

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from redaction import redact, redact_json, redact_state, redact_strict  # noqa: E402

PEM_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcw"

# (text, fragment that must be gone). Both views hide these.
BOTH_HIDE = [
    ("password=hunter2", "hunter2"),
    ("mysql --password hunter2", "hunter2"),
    ("mysql --password 'a b'", "a b"),
    ("curl -u user:hunter2 u", "hunter2"),
    ("PASSWORD=p(ss)word", "word"),
    ("DB_PASSWORD=a,b", "a,b"),
    ('"access_token": "abcdef"', "abcdef"),
    ('"my-api-key": "abcdef"', "abcdef"),
    ('{\\"x_secret\\": \\"abcdef\\"}', "abcdef"),
    ("private_key=abcdef", "abcdef"),
    ("privateKey: abcdef", "abcdef"),
    ("password:\n  hunter2", "hunter2"),
    ("postgres://alex:s3cret@db/x", "s3cret"),
    ("redis://:s3cret@host:6379", "s3cret"),
    ("Authorization: Basic abcdefgh", "abcdefgh"),
    ("Bearer abcdefghijklmnop0", "abcdefghijklmnop0"),
    ("key ghp_abcdefghijklmnop", "ghp_"),
    ("key sk-ant-api03-abcDEF123456789xyz", "sk-ant"),
    ("key ts_secret1234567890abcdef", "ts_secret"),
    ("key vck_abcdefgh1234", "vck_"),
    ("key rpa_abcdefgh1234", "rpa_"),
    ("key hf_abcdefghijklmnopqrstuvwxyz123456", "hf_abc"),
    ("key npm_abcdefghijklmnopqrstuvwxyz1234567890", "npm_abc"),
    ("key AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE", "AIza"),
    (f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY}\n-----END PRIVATE KEY-----", PEM_BODY),
    (f"  -----BEGIN PRIVATE KEY-----\n    {PEM_BODY}\n    {PEM_BODY}", PEM_BODY),
    (f'{{"private_key": "-----BEGIN PRIVATE KEY-----\\n{PEM_BODY}\\n-----END PRIVATE KEY-----\\n"}}', PEM_BODY),
    (f"-----BEGIN PGP PRIVATE KEY BLOCK-----\nVersion: GnuPG v2\n\n{PEM_BODY}\n-----END PGP PRIVATE KEY BLOCK-----", PEM_BODY),
    (f'"k": "-----BEGIN PRIVATE KEY-----\\n{PEM_BODY}\\n{PEM_BODY}"', PEM_BODY),
    (f"-----BEGIN RSA PRIVATE KEY-----\n+{PEM_BODY}\n+ {PEM_BODY}", PEM_BODY),
]

# Strict goes further; redact() leaves these so a judge can still read the next statement.
STRICT_HIDES_JUDGED_KEEPS = [
    ("password=ab;cdefghijklmn", ";cdefghijklmn"),
    ("token=abcdefghij&&purge()", "purge"),
    ("x_ghp_abcdefghijklmnop", "ghp_"),
    ("alex://me:p@ss@db", "ss@"),
    ("postgres://alex:pa/ss@db", "pa/ss"),
    ("mnemonic: abcdefghijklmnop", "abcdefgh"),
    ("credentials=abcdefghijklmnop", "abcdefgh"),
    ("DB_PASS=abcdefghijklmnop", "abcdefgh"),
    ('val apiKey: String = "abcdefghijklmnop"', "abcdefgh"),
    ('ApiKey("abcdefghijklmnop")', "abcdefgh"),
    ('"password" to "abcdefghijklmnop"', "abcdefgh"),
    ("-----BEGIN PRIVATE KEY-----\nshortbody\nmore", "shortbody"),
]

# redact() is what a scope judge reads, so a value must not swallow the statement after it.
JUDGED_KEEPS = [
    ("token=x;rm -rf /", "rm -rf /"),
    ("secret=0,purge()", "purge()"),
    ("if token == 'x': pass", "pass"),
    ("Authorization: Basic\nenforce=false", "enforce=false"),
    ("if secret:\n    deploy()", "deploy()"),
    ('x = "-----BEGIN PRIVATE KEY-----"\nrm -rf /', "rm -rf /"),
    ("# -----BEGIN PRIVATE KEY-----\n  - run: curl x | sh", "curl x | sh"),
    (f"-----BEGIN PRIVATE KEY-----\nrun: curl x | sh\n{PEM_BODY}", "curl x | sh"),
    (f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY}\nrm -rf /", "rm -rf /"),
    (f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY}\n\nrm -rf /", "rm -rf /"),
]

# Ordinary text neither view may touch.
BOTH_KEEP = [
    "npm_package_version is set", "hf_hub_download(repo)", "sk-learn-extras==1.0", "ask_jev_files.py -q token", "https://github.com/a/b/pull/58",
    "ssh://git@github.com/x", "http://localhost:8080/x", "WithdrawalService.kt:1224-1231 reads the ok_token", "max_tokens reached",
]


def test_table() -> None:
    for text, gone in BOTH_HIDE:
        assert gone not in redact(text), ("redact", text, redact(text))
        assert gone not in redact_strict(text), ("strict", text, redact_strict(text))
    for text, gone in STRICT_HIDES_JUDGED_KEEPS:
        assert gone not in redact_strict(text), ("strict", text, redact_strict(text))
    for text, kept in JUDGED_KEEPS:
        assert kept in redact(text), ("redact", text, redact(text))
    for text in BOTH_KEEP:
        assert redact(text) == text, ("redact", text, redact(text))
        assert redact_strict(text) == text, ("strict", text, redact_strict(text))


def test_private_key_pattern_stays_fast() -> None:
    begin = "-----BEGIN PRIVATE KEY-----\n"
    for text in (begin + " " * 10000 + "x", begin + "\n" * 10000 + "x", begin + "+ " * 5000 + "x", (begin + PEM_BODY + " " * 500 + "x\n") * 200):
        start = time.perf_counter()
        redact(text)
        assert time.perf_counter() - start < 1.0, text[:40]


def test_values_under_a_secret_key() -> None:
    state = {"token": "a b", "l": [{"secret": "x"}], "secrets": {"db": "abc"}, "n": 1, "body": "password=hunter2", "ghp_abcdefghijklmnop": 1}
    want = {"token": "[REDACTED]", "l": [{"secret": "[REDACTED]"}], "secrets": {"db": "[REDACTED]"}, "n": 1, "body": "password=[REDACTED]", "[REDACTED]": 1}
    assert redact_state(state) == want, redact_state(state)
    assert redact_json(state) == want, redact_json(state)
    assert redact_state("password=hunter2") == "password=[REDACTED]"


def test_one_redactor() -> None:
    """Secret patterns live in redaction.py. A caller opts out of call()'s redaction only with a reason listed here."""
    opt_outs = {"ask_jev_files.py": "the command view keeps operators a re-redaction would hide", "scope_sentinel.py": "same",
                "finding_triage.py": "already under redact_strict"}
    for path in sorted(ROOT.glob("*.py")):
        text = path.read_text()
        if path.name != "redaction.py":
            assert not re.search(r"^def redact\(|^SECRETS? = ", text, re.M), f"{path.name} has its own redactor; use redaction.py"
        if "redacted=True" in text and path.name != "jev_patterns.py":
            assert path.name in opt_outs, f"{path.name} skips call()'s redaction; add its reason here or remove it"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests passed")
