#!/usr/bin/env bash
# Live smoke: run one canned prompt in a host, then print the newest matching log row.
# Usage: smoke.sh <claude|codex|agy> <bash|write|compact|ask|ask-skill|skill> [--read]
# --read skips the host run and prints the newest row for that host and feature.
# Evidence goes in the PR body; nothing under .local/ is ever committed.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() { echo "usage: smoke.sh <claude|codex|agy> <bash|write|compact|ask|ask-skill|skill> [--read]" >&2; exit 64; }
[ $# -ge 2 ] && [ $# -le 3 ] || usage
host="$1"; feature="$2"; read_only=0
case "$host" in claude|codex|agy) ;; *) usage ;; esac
case "$feature" in bash|write|compact|ask|ask-skill|skill) ;; *) usage ;; esac
if [ $# -eq 3 ]; then [ "$3" = "--read" ] && read_only=1 || usage; fi

logdir="${JEV_LOG_DIR:-${CLAUDE_PROJECT_DIR:-$here}/.local}"
case "$feature" in compact) file=compact.jsonl ;; *) file=sentinel.jsonl ;; esac

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
keys = ("host", "host_model", "jev_model", "gate", "would_block", "tier", "error")
print(" ".join(f"{k}={hit[k]}" for k in keys if k in hit))
PY
}

if [ "$read_only" -eq 1 ]; then
  newest 0 || { echo "no $feature row for $host in $logdir/$file" >&2; exit 1; }
  exit $?
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

if [ "$host" = "codex" ]; then
  echo "Codex cannot run headless with project hooks from here. Steps:"
  echo "  1. Run 'codex' interactively in this repo and trust the hooks in /hooks."
  echo "  2. Send a prompt that makes it run one shell command."
  echo "  3. Run: bash smoke.sh codex $feature --read"
  exit 0
fi

case "$host:$feature" in
  claude:bash|claude:write|agy:bash|agy:write) ;;
  *) echo "smoke.sh $host $feature is wired in a later phase" >&2; exit 0 ;;
esac

case "$feature" in
  bash) prompt="Run ls -la and stop." ;;
  write) prompt="Use your file-writing tool (not the shell) to create a file named smoke-note.txt containing the word hello, then delete it." ;;
esac

start=$(date +%s)
cd "$here" || exit 1
case "$host" in
  claude) claude -p --dangerously-skip-permissions --output-format text "$prompt" </dev/null >/dev/null ;;
  agy) agy --dangerously-skip-permissions -p "$prompt" </dev/null >/dev/null ;;
esac
rm -f "$here/smoke-note.txt"
for _ in $(seq 1 30); do
  newest "$start" && exit 0
  sleep 0.5
done
echo "no $host $feature row after 15 s in $logdir/$file" >&2
exit 1
