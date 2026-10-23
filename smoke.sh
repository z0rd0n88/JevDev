#!/usr/bin/env bash
# Live smoke: run one canned prompt in a host, then print the newest matching log row.
# Usage: smoke.sh <claude|codex|agy> <router|bash|write|compact|ask|ask-skill|skill> [--read] [--user]
# --user runs from /home/alex/BotHaus (no project hooks) and reads ~/.local/state/jevdev/.
# --read skips the host run and prints the newest row for that host and feature.
# Evidence goes in the PR body; nothing under .local/ is ever committed.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() { echo "usage: smoke.sh <claude|codex|agy> <router|bash|write|compact|ask|ask-skill|skill> [--read] [--user]" >&2; exit 64; }
[ $# -ge 2 ] && [ $# -le 4 ] || usage
host="$1"; feature="$2"; read_only=0; user_scope=0
case "$host" in claude|codex|agy) ;; *) usage ;; esac
case "$feature" in router|bash|write|compact|ask|ask-skill|skill) ;; *) usage ;; esac
shift 2
for a in "$@"; do
  case "$a" in --read) read_only=1 ;; --user) user_scope=1 ;; *) usage ;; esac
done

workdir="$here"; logdir="${JEV_LOG_DIR:-${CLAUDE_PROJECT_DIR:-$here}/.local}"
if [ "$user_scope" -eq 1 ]; then workdir=/home/alex/BotHaus; logdir="${JEV_LOG_DIR:-$HOME/.local/state/jevdev}"; fi
case "$feature" in router) file=router.jsonl ;; compact) file=compact.jsonl ;; *) file=sentinel.jsonl ;; esac

# Print the newest row of $file for this host and feature with ts >= $1; exit 0 on a hit, 1 otherwise.
newest() {
  python3 - "$logdir/$file" "$host" "$feature" "$1" <<'PY'
import json, sys
path, host, feature, since = sys.argv[1:]
hit = None
try:
    lines = open(path).read().splitlines()
except OSError:
    lines = []
for line in lines:
    try:
        row = json.loads(line)
    except ValueError:
        continue
    if row.get("host") != host or row.get("ts", 0) < float(since):
        continue
    if feature in ("bash", "write") and row.get("gate") != feature:
        continue
    if feature in ("ask", "ask-skill") and "ask_jev_files.py" not in (row.get("command") or ""):
        continue
    hit = row
if hit is None:
    sys.exit(1)
keys = ("host", "host_model", "jev_model", "router_version", "roster_sha256", "suggestion", "gate", "would_block", "tier", "printed", "error")
print(" ".join(f"{k}={hit[k]}" for k in keys if k in hit))
PY
}

if [ "$read_only" -eq 1 ]; then
  newest 0 || { echo "no $feature row for $host in $logdir/$file" >&2; exit 1; }
  exit $?
fi

if [ "$feature" = "router" ]; then
  echo "Verify the prompt hook in an interactive session:"
  echo "  1. Open '$host' in $workdir; in Codex, review the changed hooks in /hooks."
  echo "  2. Ask: Help me create a reusable agent skill."
  echo "  3. Run: bash smoke.sh $host router --read$( [ "$user_scope" -eq 1 ] && echo ' --user' )."
  echo "  4. Check host, host_model, router_version, roster_sha256, and suggestion (or an explicit error)."
  exit 0
fi

skill_prompt="/hyper-jev Reply with only the first line of the Purpose section of this skill."
if [ "$feature" = "skill" ]; then
  cd "$here" || exit 1
  case "$host" in
    claude) claude -p --output-format text "$skill_prompt" </dev/null ;;
    agy) agy -p "$skill_prompt" </dev/null ;;
    codex)
      echo "Codex cannot run a skill headless from here. Steps:"
      echo "  1. Open 'codex' in this repo and confirm /skills lists hyper-jev."
      echo "  2. Type: \$hyper-jev Reply with only the first line of the Purpose section of this skill."
      echo "  3. Expect: Turn the user's request into a small, tested Jev integration."
      ;;
  esac
  exit $?
fi

ask_skill_prompt="/ask-jev Triage the result of python3 tests/test_sentinel.py and tell me the kind of failure with its confidence."
if [ "$feature" = "ask-skill" ] && [ "$host" = "codex" ]; then
  echo "Codex cannot run a skill headless from here. Steps:"
  echo "  1. Open 'codex' in this repo, trust the hooks in /hooks, and confirm /skills lists ask-jev."
  echo "  2. Type: \$ask-jev Triage the result of python3 tests/test_sentinel.py and tell me the kind of failure with its confidence."
  echo "  3. Expect: a reply naming a kind label with a confidence."
  echo "  4. Run: bash smoke.sh codex ask-skill --read"
  exit 0
fi

if [ "$feature" = "compact" ]; then
  echo "The advisor fires at Stop (Claude/Codex) or PostInvocation (agy). Steps:"
  echo "  1. In your shell: export JEV_COMPACT_LINES=1000,2000,3000"
  echo "  2. Open '$host' interactively in this repo$( [ "$host" = codex ] && echo " and trust the hooks in /hooks")."
  echo "  3. Send two short prompts on different topics (for example: 'say hi', then 'write a haiku about rain')."
  echo "  4. After the second turn, look for the advisor's message in the host UI."
  echo "  5. Run: bash smoke.sh $host compact --read"
  echo "  6. Expect tier other than silent, printed=True, jev_model typesafe/jev-…; note 'message seen: yes/no'."
  exit 0
fi

if [ "$host" = "codex" ]; then
  echo "Codex cannot run headless with project hooks from here. Steps:"
  echo "  1. Run 'codex' interactively in this repo and trust the hooks in /hooks."
  echo "  2. Send a prompt that makes it run one shell command."
  echo "  3. Run: bash smoke.sh codex $feature --read"
  exit 0
fi

case "$host:$feature" in
  claude:bash|claude:write|claude:ask|claude:ask-skill|agy:bash|agy:write|agy:ask|agy:ask-skill) ;;
  *) echo "smoke.sh $host $feature is wired in a later phase" >&2; exit 0 ;;
esac

case "$feature" in
  bash) prompt="Run ls -la and stop." ;;
  write) prompt="Use your file-writing tool (not the shell) to create a file named smoke-note.txt containing the word hello, then delete it." ;;
  ask)
    # The triage question object of the ask-jev skill, as one line.
    q='{"kind":{"type":"choice","instructions":"What kind of failure is `output`?","criteria":{"bug_in_code":"The code under test misbehaves","wrong_test":"The test asserts the wrong expectation","environment":"A missing dependency, key, file, or service","none":"The run passed","other":"Something else"}},"flaky":{"type":"noul","instructions":"Is `output` a real failure rather than a flaky one?","criteria":{"true":"Deterministic assertion or error text","false":"Timeouts, network, or ordering that could pass on retry"}}}'
    prompt="Run: bash with_jev_key.sh python3 ask_jev_files.py ask --command 'python3 tests/test_sentinel.py' -q '$q' and report the answers." ;;
esac

start=$(date +%s)
cd "$workdir" || exit 1
if [ "$feature" = "ask-skill" ]; then
  case "$host" in
    claude) claude -p --dangerously-skip-permissions --output-format text "$ask_skill_prompt" </dev/null ;;
    agy) agy --dangerously-skip-permissions -p "$ask_skill_prompt" </dev/null ;;
  esac
else
case "$host" in
  claude) claude -p --dangerously-skip-permissions --output-format text "$prompt" </dev/null >/dev/null ;;
  agy) agy --dangerously-skip-permissions -p "$prompt" </dev/null >/dev/null ;;
esac
fi
rm -f "$here/smoke-note.txt"
for _ in $(seq 1 30); do
  newest "$start" && exit 0
  sleep 0.5
done
echo "no $host $feature row after 15 s in $logdir/$file" >&2
exit 1
