"""Secret redaction: the one place secret patterns live. Stdlib only, because jev_patterns imports it.

Two views, because what the text is for decides which mistake is worse. Both are best effort, not a guarantee.

  redact()         Text a scope judge reads. A value must not swallow the statement after it, or code could hide from the
                   judge, so it stops at statement punctuation and accepts the leaks listed below.
  redact_strict()  Text only ever read for its content (review reports, code hunks in the findings corpus). It fails closed: a
                   redacted `tokenizer = ...` costs nothing here and a missed secret does. It is everything redact() hides, and more.

jev_patterns.call() applies redact_state() to every state unless the caller says the state is already redacted.
Shell commands go through scope_sentinel.command_view() instead. tests/test_redaction.py holds the contract.
"""

from __future__ import annotations

import re

SECRET_WORDS = r"token|secret|password|passwd|api[_-]?key|private[_-]?key"
_VALUE = r"""(?:[^\s'";,`$]|\$(?!\()|,(?![A-Za-z_][\w.]{0,64}[(= \t])){1,4096}"""
_LINE_BREAK = r"(?:\r?\n|\\r?\\n)"
# Each pattern keeps group 1 (possibly empty) and replaces the rest of the match. Keyword-to-value whitespace is
# [ \t], never \s, so a match never crosses a newline, except a PEM body and a key alone on its line (pattern 1).
# ponytail: every name containing token/secret/password/key loses its value (max_tokens=1024 too); redact_count reports it.
# Every run before a required delimiter is capped ({0,64}, {1,64}) so repeated keywords stay linear; a bare value ends at
# whitespace, ;, backtick, $( or a , followed by code, so one statement cannot hide the next while ( ) and a plain , stay
# hidden; a quoted value ends at its closing quote, and the PEM body is base64 or `Name: value` lines.
# ponytail: in file text `password=ab;cd` leaks ;cd, an unindented or backslash-continued next-line value leaks, and && and |
# still hide what follows; tell them apart by language if verdicts need it. Commands go through command_view() instead.
SECRETS = [re.compile(p) for p in (
    r"(?im)(^[+-]?[ \t]*['\"]?\w{0,64}(?:" + SECRET_WORDS + r")\w{0,64}['\"]?[ \t]*(?::[ \t]{0,64}(?:[|>][+-]?[ \t]{0,64})?|=[ \t]{0,64}\([ \t]{0,64})\r?\n[+-]?[ \t]+)"
    r"(?:(['\"])[^'\"\n]{1,4096}\2|" + _VALUE + r")(?=[ \t]*\r?$)",
    r"(?i)(authorization:[ \t]*\S{1,64}[ \t]+)" + _VALUE,
    r"(?i)(bearer[ \t]+)[A-Za-z0-9._~+/=-]{16,}",
    r"(?i)((?:" + SECRET_WORDS + r")\w{0,64}[ \t]*(?:=(?!=)|:=?)[ \t]*)(?:\$?(['\"])[^'\"\n]{1,4096}\2|['\"]?" + _VALUE + ")",
    r"""(?i)(\\?["'][\w-]{0,64}(?:""" + SECRET_WORDS + r"""\w{0,64})[\w-]{0,64}\\?["'][ \t]*:[ \t]*\\?["'])(?:\\[^"'\n]|[^"'\\\n])+""",
    r"(?i)(--(?:" + SECRET_WORDS + r")[= \t]+)(?:(['\"])[^'\"\n]{1,4096}\2|" + _VALUE + ")",
    r"(\s-u[ \t]+[^\s:'\"]{1,64}:)" + _VALUE,
    r"(://[^/\s:@]*:)[^/\s@]+(?=@)",
    r"()\b(?:gh[pousr]_|github_pat_|glpat-)[\w-]{10,}",
    r"()\bsk[-_](?=[\w-]{0,64}\d)[\w-]{20,}",
    r"()\bts_[\w-]{16,}",
    r"()\b(?:vck|rpa)_[\w-]{8,}",
    r"()\b(?:hf|npm)_[A-Za-z0-9]{30,}",
    r"()\bAIza[\w-]{20,}",
    r"()\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"()\bxox[abposr]-[\w-]{10,}",
    r"()\beyJ[\w-]{10,256}\.[\w-]{10,}\.[\w-]{10,}",
    r"(-----BEGIN [A-Z ]{0,32}PRIVATE KEY(?: BLOCK)?-----)(?:" + _LINE_BREAK + r"[ \t]*[+-]?[ \t]*(?:[A-Za-z0-9+/=]{12,}|[\w-]{1,64}:[^\r\n\\]{0,256}|)[ \t]*(?=" + _LINE_BREAK + r"|\Z))+",
)]

# --- redact_strict(): known shapes first, a truncated private key to the end of the text. `sk`, `hf` and `npm` also start
# ordinary names (`sk-learn`, `hf_hub_download`, `npm_package_version`), so those need the key's own shape.
_PEM = r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z ]*PRIVATE KEY(?: BLOCK)?-----|\Z)"
_PEM_BLOCK = re.compile(_PEM, re.S)
_TOKEN = re.compile(
    r"(?:(?<![A-Za-z0-9])|(?<=\\[nrt]))(?:ghp|gho|ghu|ghs|github_pat|xox[a-z]|vck|glpat|rpa)[-_][A-Za-z0-9_-]{8,}"
    r"|(?:(?<![A-Za-z0-9_])|(?<=\\[nrt]))(?:sk[-_](?=[A-Za-z_-]{0,40}\d)[A-Za-z0-9_-]{12,}|(?:hf|npm)_[A-Za-z0-9]{30,})"
    r"|AKIA[A-Z0-9]{12,}|AIza[0-9A-Za-z_-]{20,}"
    r"|Bearer [A-Za-z0-9._-]{12,}"
    r"|eyJ[A-Za-z0-9_-]{10,2048}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]*)?"
    rf"|{_PEM}",
    re.S,
)
# A keyword anywhere in an identifier, then `=`, `:`, `:=`, `=>`, a typed declaration, or a quoted `to "..."` / `("...")`.
# A value runs to whitespace, a quote, a backtick, or a `\"` / `\\` from JSON quoted as text. Decode JSON first when it must stay
# parseable (redact_json); the text path does not promise that.
_STRICT_WORD = SECRET_WORDS + r"|pwd|passphrase|mnemonic|credential|[_-]pass(?![a-z])"
_OPERATOR = r"\\*[\"'`]?(?:\s*:\s*[A-Za-z_][\w.<>?, ]{0,60}\s*=|\s*:=|\s*=>|\s*[=:]|\s+to\s+(?=\\*[\"'])|\((?=\\*[\"']))\s*\\*[\"'`]?"
_VALUE_CHAR = r"(?:[^\\\"'`\s]|\\(?![\\\"]))"
_ASSIGNED = re.compile(rf"(?i)((?:{_STRICT_WORD})[A-Za-z0-9_-]{{0,80}})({_OPERATOR}){_VALUE_CHAR}{{12,}}")
_SECRET_KEY = re.compile(_STRICT_WORD, re.I)
# URL credentials, per run of text with string search: no length cap to slip past, and linear on a run of URLs. Anything from
# the first `://user:` to the last `@` in the run goes, so a port and path with an `@` in it is redacted too.
_URL_RUN = re.compile(r"(?:[^\\\s\"']|\\(?![\\\"]))+")
_URL_USER = re.compile(r"://(?:[^/:]*:|[^/:@]{16,}(?=@))")


def redact(text: str) -> str:
    for pattern in SECRETS:
        text = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    return text


def redact_count(text: str) -> tuple[str, int]:
    """redact() plus the number of substitutions across all patterns."""
    total = 0
    for pattern in SECRETS:
        text, n = pattern.subn(lambda m: f"{m.group(1)}[REDACTED]", text)
        total += n
    return text, total


def _redact_userinfo(m: re.Match) -> str:
    run = m.group(0)
    user = _URL_USER.search(run)
    at = run.rfind("@", user.end()) if user else -1
    return run if at < 0 else f"{run[:user.start()]}://[REDACTED]@{run[at + 1:]}"


def redact_strict(text: str) -> str:
    text = _TOKEN.sub("[REDACTED]", text)
    text = _ASSIGNED.sub(r"\1\2[REDACTED]", text)
    return redact(_URL_RUN.sub(_redact_userinfo, text))


def blank_private_keys(text: str) -> str:
    """Private-key blocks across a whole file, line count kept: a window cut from inside a key has no BEGIN or END to find."""
    return _PEM_BLOCK.sub(lambda m: "\n".join("[REDACTED]" for _ in m.group(0).split("\n")), text)


def _walk(value, scrub, key: str = ""):
    """Strings by content, and whole under a key that names a secret, since no `key=` is left to match once decoded."""
    if isinstance(value, str):
        return "[REDACTED]" if value and _SECRET_KEY.search(key) else scrub(value)
    if isinstance(value, list):
        return [_walk(v, scrub, key) for v in value]
    if isinstance(value, dict):
        return {scrub(k): _walk(v, scrub, k if _SECRET_KEY.search(k) else key) for k, v in value.items()}
    return value


def redact_state(value):
    """redact() over a decoded JSON value or a string."""
    return _walk(value, redact)


def redact_json(value):
    """redact_strict() over a decoded JSON value or a string."""
    return _walk(value, redact_strict)
