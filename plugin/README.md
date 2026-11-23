# jev plugin

This repo doubles as the `jev` Claude Code plugin. The plugin root is the repo root; `.claude-plugin/plugin.json` points at the pieces below. `pruner/` stays its own plugin, `jev-pruner`.

```
/plugin marketplace add z0rd0n88/z0rd0nlander
/plugin install jev@z0rd0nlander
```

| Piece | Where | On by default |
|---|---|---|
| `ask-jev`, `hyper-jev` skills | `.agents/skills/` | yes |
| `jev`, `jev-selfcheck`, `ask-jev-files` CLIs | `bin/` (Claude Code puts a plugin's `bin/` on the Bash tool's PATH) | yes |
| Skill router (`UserPromptSubmit`, up to 90 s) | `skill_router.py` | no |
| Scope Sentinel (`PreToolUse` on Bash and writes, shadow mode) | `scope_sentinel.py` | no |
| Compaction advisor (`Stop`) | `compact_advisor.py` | no |

## Turning hooks on

Every hook goes through `plugin/jev-hook.sh`, which exits at once unless `JEV_HOOKS` names it. Set it in the `env` block of `~/.claude/settings.json` (or a project's settings):

```json
{ "env": { "JEV_HOOKS": "sentinel,advisor" } }
```

Values: a comma list of `router`, `sentinel`, `advisor`, or `1` / `all` for every hook. With the hooks off the plugin costs one `bash` start per event and no Jev calls.

- A project whose `.claude/settings.json` already runs the same script (JevDev itself) keeps its project hook; the plugin's copy stands down, so nothing fires twice there.
- If `~/.claude/settings.json` also carries the user-scope hooks that `install_user.py` prints, leave those out of `JEV_HOOKS` or remove them, or they run twice.
- Logs go to `$JEV_LOG_DIR`, default `~/.local/state/jevdev`, never into the project.

## Requirements

- Python 3.11+, `PyYAML`, `jq`, curl 7.76+ on the machine the session runs on.
- A Jev key in `TYPESAFE_API_KEY` or `OPENROUTER_API_KEY`, in the environment or in `~/.secrets` (read by `with_jev_key.sh`).
