"""Tests for the Benchmark Fixture Curator."""

import os
from pathlib import Path
import importlib.util

SOURCE = Path(__file__).parents[1] / "fixture_curator.py"

def load_module():
    spec = importlib.util.spec_from_file_location("fixture_curator", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_deterministic_checks():
    module = load_module()
    
    # Missing fields
    bad_record = {"text": "foo"}
    errors = module.validate_record(bad_record)
    assert "Missing required field: id" in errors, f"Got: {errors}"
    assert "Missing required field: gold" in errors
    
    
    # Valid record
    good_record = {"id": "123", "text": "do something", "gold": "some_skill"}
    assert not module.validate_record(good_record)
    
    # Null gold is allowed
    null_gold_record = {"id": "456", "text": "hello", "gold": None}
    assert not module.validate_record(null_gold_record)

def test_duplicate_ids():
    module = load_module()
    
    records = [
        {"id": "1", "text": "a", "gold": "x"},
        {"id": "2", "text": "b", "gold": "y"},
        {"id": "1", "text": "c", "gold": "z"}
    ]
    dupes = module.find_duplicates(records)
    assert "1" in dupes
    assert "2" not in dupes

def test_jev_questions_format():
    module = load_module()
    
    # Test that the question structure aligns with our expectations for Jev
    questions = module.build_curator_questions()
    
    assert "self_contained" in questions
    assert questions["self_contained"]["type"] == "noul"
    
    assert "multiple_defensible" in questions
    assert questions["multiple_defensible"]["type"] == "noul"

def main():
    test_deterministic_checks()
    test_duplicate_ids()
    test_jev_questions_format()
    print("All tests passed.")

if __name__ == "__main__":
    main()
