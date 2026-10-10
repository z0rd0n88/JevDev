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

def test_jev_questions():
    module = load_module()
    
    items = ["Constraint A", "Constraint B"]
    questions = module.build_jev_questions(items)
    
    assert len(questions) == 2
    assert "item_0" in questions
    assert "item_1" in questions
    assert questions["item_0"]["type"] == "choice"
    assert "missing" in questions["item_0"]["criteria"]

def main():
    test_parse_ledger()
    test_jev_questions()
    print("All tests passed.")

if __name__ == "__main__":
    main()
