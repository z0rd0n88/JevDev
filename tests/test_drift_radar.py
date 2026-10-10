"""Tests for Decision Drift Radar (Slice 1)."""

import os
from pathlib import Path
import importlib.util

SOURCE = Path(__file__).parents[1] / "drift_radar.py"

def load_module():
    spec = importlib.util.spec_from_file_location("drift_radar", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_load_diff():
    module = load_module()
    
    # Test valid file
    test_diff = Path("test_dummy.diff")
    test_diff.write_text("--- a/file\n+++ b/file\n+ added line")
    
    try:
        content = module.load_diff_file(str(test_diff))
        assert "added line" in content
    finally:
        test_diff.unlink()

def test_missing_diff():
    module = load_module()
    
    try:
        module.load_diff_file("nonexistent.diff")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass

def test_jev_questions():
    module = load_module()
    questions = module.build_jev_questions()
    
    assert "drift" in questions
    assert questions["drift"]["type"] == "choice"
    
    criteria = questions["drift"]["criteria"]
    assert "implements" in criteria
    assert "contradicts" in criteria
    assert "unaddressed" in criteria
    assert "defers" in criteria

def main():
    test_load_diff()
    test_missing_diff()
    test_jev_questions()
    print("All tests passed.")

if __name__ == "__main__":
    main()
