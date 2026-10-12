#!/usr/bin/env bash
# Run a command with only the Jev key loaded from ~/.secrets, so repo hook code never sees the other secrets.
if [ -r "$HOME/.secrets" ]; then
  eval "$(grep -E '^[[:space:]]*(export[[:space:]]+)?(TYPESAFE_API_KEY|OPENROUTER_API_KEY)=' "$HOME/.secrets")" 2>/dev/null
  export TYPESAFE_API_KEY OPENROUTER_API_KEY 2>/dev/null
fi
exec "$@"
