#!/usr/bin/env bash
# Hook entry for the jev plugin. Runs one Jev hook only when JEV_HOOKS turns it on, so installing the plugin adds no latency
# and no Jev calls by default. JEV_HOOKS is a comma list of router, sentinel, advisor, or 1/all for every hook.
# Usage: jev-hook.sh <router|sentinel|advisor>   (the hook payload arrives on stdin and passes through untouched)
set -u
name="${1:-}"
case "$name" in
  router) cmd=(skill_router.py --host claude hook) ;;
  sentinel) cmd=(scope_sentinel.py hook claude --user) ;;
  advisor) cmd=(compact_advisor.py hook claude --user) ;;
  *) echo "jev-hook.sh: unknown hook '$name' (want router, sentinel or advisor)" >&2; exit 64 ;;
esac
case ",${JEV_HOOKS:-}," in
  *,1,* | *,all,* | *,"$name",*) ;;
  *) exit 0 ;;
esac
# A project that already runs this script as a project hook (JevDev itself) keeps its own copy; the plugin's stands down.
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && grep -qF "${cmd[0]}" "$CLAUDE_PROJECT_DIR/.claude/settings.json" 2>/dev/null; then
  exit 0
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export JEV_BIN="${JEV_BIN:-$root/bin/jev}" JEV_LOG_DIR="${JEV_LOG_DIR:-$HOME/.local/state/jevdev}" SCOPE_SENTINEL=1
exec bash "$root/with_jev_key.sh" python3 "$root/${cmd[0]}" "${cmd[@]:1}"
