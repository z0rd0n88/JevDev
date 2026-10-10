#!/usr/bin/env python3
"""Test Intent Escrow (Slice 1).

Judges whether an edited assertion still protects the previously stated behavior.
"""

import argparse
from pathlib import Path
import sys

def load_diff_file(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Diff file not found: {path}")
    return path.read_text(encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Test Intent Escrow")
    parser.add_argument("--diff", required=True, help="Path to the test diff file")
    
    args = parser.parse_args()
    
    try:
        diff_content = load_diff_file(args.diff)
        print(f"Loaded test diff ({len(diff_content)} bytes).")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
