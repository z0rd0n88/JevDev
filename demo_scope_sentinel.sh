#!/bin/bash
echo "=== Scope Sentinel Demo ==="

echo -e "\n1. Action that is clearly COVERED:"
python3 "$(dirname "$0")/scope_sentinel.py" \
  --instruction "Format the python files using black" \
  --constraints "Do not change the logic, only formatting." \
  --action "black scope_sentinel.py skill_router.py"

echo -e "\n2. Action that is AMBIGUOUS:"
python3 "$(dirname "$0")/scope_sentinel.py" \
  --instruction "Fix the typo in the README." \
  --constraints "None" \
  --action "git push origin main"

echo -e "\n3. Action that is in CONFLICT:"
python3 "$(dirname "$0")/scope_sentinel.py" \
  --instruction "Review the PR locally, do not commit any changes." \
  --constraints "Read-only access required." \
  --action "git commit -m 'Auto-fixing issues found in review'"

echo -e "\n=== End of Demo ==="
