"""bin/jev keeps the API key out of curl's argv, where any local user can read it with `ps`."""

from pathlib import Path
import subprocess
import tempfile


JEV = Path(__file__).parents[1] / "bin/jev"
KEY = "sk-or-test-not-a-real-key"

# Stand-in curl: records its argv and stdin, then answers like Jev.
FAKE_CURL = """#!/bin/sh
here=$(dirname "$0")
printf '%s\\n' "$@" > "$here/argv"
cat > "$here/stdin"
echo '{"answers":{"q":{"type":"noul","noul":0.9}}}'
"""


def run(tmp, **env):
    subprocess.run(
        [str(JEV), "Is this a test?", "state"],
        env={"PATH": f"{tmp}:/usr/bin:/bin", **env},
        check=True,
        capture_output=True,
    )
    return Path(tmp, "argv").read_text(), Path(tmp, "stdin").read_text()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        curl = Path(tmp, "curl")
        curl.write_text(FAKE_CURL)
        curl.chmod(0o755)

        argv, stdin = run(tmp, OPENROUTER_API_KEY=KEY)
        assert KEY not in argv, "key leaked into curl argv"
        assert "https://openrouter.ai/api/v1/systemone" in argv.splitlines(), argv
        assert stdin == f"Authorization: Bearer {KEY}\n", "auth header not on curl stdin"

        argv, stdin = run(
            tmp,
            OPENROUTER_API_KEY=KEY,
            JEV_BASE_URL="http://127.0.0.1:9",
            JEV_ALLOW_LOCAL="1",
        )
        assert KEY not in argv + stdin, "key sent to a local server"
        assert "@-" not in argv.splitlines(), "local route still reads a header from stdin"
    print("ok: key stays off curl argv; local route gets no key")


if __name__ == "__main__":
    main()
