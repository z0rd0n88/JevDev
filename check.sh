#!/usr/bin/env bash
# Every check CI runs: lint, then each test file in its own process, since several point JEV_BIN at a stub before importing.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
status=0
ruff check . || status=1
for f in tests/test_*.py; do
  if output=$(python3 "$f" 2>&1); then
    echo "ok   $f"
  else
    echo "FAIL $f"
    echo "$output" | tail -20
    status=1
  fi
done
exit "$status"
