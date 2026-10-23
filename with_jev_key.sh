#!/usr/bin/env bash
# Run one of JevDev's Jev scripts with only the Jev key loaded from ~/.secrets, so repo hook code never sees the
# other secrets and the key never reaches any other command. Keys and JEV_BIN from the caller are dropped.
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
script=$(realpath -e -- "${2:-/nonexistent}" 2>/dev/null)
case $script in
  "$here"/scope_sentinel.py | "$here"/compact_advisor.py | "$here"/skill_router.py | \
  "$here"/ask_jev_files.py | "$here"/handoff_check.py | "$here"/fixture_curator.py) ;;
  *) script= ;;
esac
if [ "${1-}" != python3 ] || [ -z "$script" ]; then
  echo "with_jev_key.sh: runs only 'python3 <JevDev Jev script> ...' from $here; refused: ${1-} ${2-}" >&2
  exit 64
fi
unset TYPESAFE_API_KEY OPENROUTER_API_KEY JEV_BIN
if [ -r "$HOME/.secrets" ]; then
  eval "$(grep -E '^[[:space:]]*(export[[:space:]]+)?(TYPESAFE_API_KEY|OPENROUTER_API_KEY)=' "$HOME/.secrets")" 2>/dev/null
  export TYPESAFE_API_KEY OPENROUTER_API_KEY 2>/dev/null
fi
exec python3 "$script" "${@:3}"
