"""Tests for Test Intent Escrow (Slice 1)."""

import os
from pathlib import Path
import importlib.util

SOURCE = Path(__file__).parents[1] / "test_escrow.py"

def load_module():
    spec = importlib.util.spec_from_file_location("test_escrow", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_load_diff():
    module = load_module()
    
    test_diff = Path("test_dummy.diff")
    test_diff.write_text("--- a/test_file.py\n+++ b/test_file.py\n- assert x == 1\n+ assert x > 0")
    
    try:
        content = module.load_diff_file(str(test_diff))
        assert "assert x > 0" in content
    finally:
        test_diff.unlink()

def test_jev_questions():
    module = load_module()
    
    questions = module.build_jev_questions()
    
    assert "intent" in questions
    assert questions["intent"]["type"] == "choice"
    assert "weakened" in questions["intent"]["criteria"]
    assert "protects" in questions["intent"]["criteria"]

def main():
    test_load_diff()
    test_jev_questions()
    print("All tests passed.")

if __name__ == "__main__":
    main()
