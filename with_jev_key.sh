#!/usr/bin/env bash
# Run a command with only the Jev key loaded from ~/.config/secrets/shell.env, so repo hook code never sees the other secrets.
if [ -r "$HOME/.config/secrets/shell.env" ]; then
  eval "$(grep -E '^[[:space:]]*(export[[:space:]]+)?(TYPESAFE_API_KEY|OPENROUTER_API_KEY)=' "$HOME/.config/secrets/shell.env")" 2>/dev/null
  export TYPESAFE_API_KEY OPENROUTER_API_KEY 2>/dev/null
fi
exec "$@"
