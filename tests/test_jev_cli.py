"""bin/jev keeps the API key out of curl's argv, where any local user can read it with `ps`."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


JEV = Path(__file__).parents[1] / "bin/jev"
KEY = "sk-or-test-not-a-real-key"
STATE = "STATE-MARKER"
QUESTION = "QUESTION-MARKER"

# Stand-in curl: records its argv, stdin and the --data-binary file, then answers like Jev.
FAKE_CURL = """#!/bin/sh
here=$(dirname "$0")
printf '%s\\n' "$@" > "$here/argv"
cat > "$here/stdin"
for a; do [ "${p-}" = --data-binary ] && cat "${a#@}" > "$here/body"; p=$a; done
echo '{"answers":{"q":{"type":"noul","noul":0.9}}}'
"""

# Stand-in jq: refuses $ENV (jq 1.6+ only), records its argv (never its stdin), then runs the real jq.
FAKE_JQ = """#!/bin/sh
for a; do case $a in *'$ENV'*) echo 'jq 1.5 has no $ENV' >&2; exit 3;; esac; done
printf '%s\\n' "$@" >> "$(dirname "$0")/jqargv"
exec {} "$@"
"""


def jev(tmp, *args, **env):
    return subprocess.run(
        [str(JEV), *args],
        env={"PATH": f"{tmp}:{os.environ['PATH']}", **env},
        input=STATE,
        capture_output=True,
        text=True,
    )


def run(tmp, **env):
    for f in ("body", "jqargv"):
        Path(tmp, f).unlink(missing_ok=True)
    r = jev(tmp, QUESTION, **env)
    assert r.returncode == 0, r.stderr
    return [Path(tmp, f).read_text() for f in ("argv", "stdin", "body", "jqargv")]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        real_jq = shutil.which("jq")
        assert real_jq, "jq not on PATH"
        for name, text in {"curl": FAKE_CURL, "jq": FAKE_JQ.format(shlex.quote(real_jq))}.items():
            Path(tmp, name).write_text(text)
            Path(tmp, name).chmod(0o755)

        argv, stdin, body, jqargv = run(tmp, OPENROUTER_API_KEY=KEY)
        assert KEY not in argv, "key leaked into curl argv"
        assert "https://openrouter.ai/api/v1/systemone" in argv.splitlines(), argv
        assert "\n-H\n@-\n" in argv, "curl not told to read the auth header from stdin"
        assert "Content-Type: application/json" in argv.splitlines(), argv
        assert stdin == f"Authorization: Bearer {KEY}\n", "auth header not on curl stdin"
        assert STATE not in argv + jqargv, "state leaked into curl or jq argv"
        sent = json.loads(body)
        assert sent["state"] == STATE, body
        assert sent["questions"]["q"]["instructions"] == QUESTION, body

        argv, stdin, body, jqargv = run(
            tmp,
            OPENROUTER_API_KEY=KEY,
            JEV_BASE_URL="http://127.0.0.1:9",
            JEV_ALLOW_LOCAL="1",
        )
        assert KEY not in argv + stdin + body, "key sent to a local server"
        assert "@-" not in argv.splitlines(), "local route still reads a header from stdin"
        assert STATE not in argv + jqargv, "state leaked into curl or jq argv"
        assert json.loads(body)["state"] == STATE, body

        # Raw -q questions go through the same jq body build.
        r = jev(tmp, "-n", "-q", '{"q":{"type":"noul","instructions":"x"}}', QUESTION, OPENROUTER_API_KEY=KEY)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["questions"]["q"]["instructions"] == "x", r.stdout

        # The JEV_BASE_URL guard refuses before -n prints anything, so no curl runs.
        r = jev(tmp, "-n", QUESTION, OPENROUTER_API_KEY=KEY, JEV_BASE_URL="https://attacker.example")
        assert r.returncode == 64, "off-route JEV_BASE_URL not refused"
        r = jev(tmp, "-n", QUESTION, OPENROUTER_API_KEY=KEY, JEV_BASE_URL="http://127.0.0.1:9")
        assert r.returncode == 64, "loopback JEV_BASE_URL accepted without JEV_ALLOW_LOCAL=1"
    print("ok: key stays off curl argv; state and body off argv; local route gets no key; guard refuses")


if __name__ == "__main__":
    main()
