#!/usr/bin/env python3
"""Decision Drift Radar (Slice 1).

Compares a recorded owner decision with a PR diff hunk to judge whether
the change implements, contradicts, or leaves the decision unaddressed.
"""

import argparse
from pathlib import Path
import sys


def load_diff_file(path_str: str) -> str:
    """Load the contents of a diff file."""
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Diff file not found: {path}")
    return path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Decision Drift Radar")
    parser.add_argument("--decision", required=True, help="The recorded owner decision text")
    parser.add_argument("--diff", required=True, help="Path to the diff file")
    
    args = parser.parse_args()
    
    try:
        diff_content = load_diff_file(args.diff)
        print(f"Loaded decision: {args.decision}")
        print(f"Loaded diff ({len(diff_content)} bytes)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
