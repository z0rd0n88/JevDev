"""Tests for Handoff Integrity Check (Slice 1)."""

import os
from pathlib import Path
import importlib.util

SOURCE = Path(__file__).parents[1] / "handoff_check.py"

def load_module():
    spec = importlib.util.spec_from_file_location("handoff_check", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_parse_ledger():
    module = load_module()
    
    content = "Constraint 1\nConstraint 2\n\nConstraint 3"
    items = module.parse_ledger(content)
    assert len(items) == 3
    assert items[0] == "Constraint 1"
    assert items[2] == "Constraint 3"

def main():
    test_parse_ledger()
    print("All tests passed.")

if __name__ == "__main__":
    main()
