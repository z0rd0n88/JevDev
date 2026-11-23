# vendor

Exact copies of code that is edited in another repository. Do not edit anything under a copied
folder: `bash check.sh` and CI fail on any difference from the lock file beside it.

| Copy | Edited in | Lock |
|---|---|---|
| `workflow-router/` | [`z0rd0n88/my-skills`](https://github.com/z0rd0n88/my-skills), `skills/workflow-router/` | `workflow-router.lock.json` |

To change the skill, change it in my-skills, then bring the copy up to date from a checkout of it:

```bash
python3 vendor_sync.py sync --source ../my-skills
```

The repo README's [Workflow router](../README.md#workflow-router) section says what the copy is
for and how the two checks work.
