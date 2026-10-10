#!/usr/bin/env python3
"""Handoff Integrity Check (Slice 1).

Compares items in a decision ledger against a handoff description.
"""

import argparse
from pathlib import Path
import sys

def parse_ledger(content: str) -> list[str]:
    """Parse a text file into a list of ledger items (ignoring blank lines)."""
    return [line.strip() for line in content.splitlines() if line.strip()]

def load_file(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Handoff Integrity Check")
    parser.add_argument("--ledger", required=True, help="Path to the decision ledger file")
    parser.add_argument("--handoff", required=True, help="Path to the handoff text file")
    
    args = parser.parse_args()
    
    try:
        ledger_content = load_file(args.ledger)
        handoff_content = load_file(args.handoff)
        
        items = parse_ledger(ledger_content)
        print(f"Loaded {len(items)} items from ledger.")
        print(f"Loaded handoff ({len(handoff_content)} bytes).")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
