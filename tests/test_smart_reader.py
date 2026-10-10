"""Tests for the Jev Smart Reader."""

import os
from pathlib import Path
import importlib.util

SOURCE = Path(__file__).parents[1] / "smart_reader.py"

def load_module():
    spec = importlib.util.spec_from_file_location("smart_reader", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_chunking():
    module = load_module()
    
    text = "\n".join(str(i) for i in range(1, 101)) # 100 lines
    chunks = module.chunk_text(text, chunk_size=30, overlap=10)
    
    # Expected chunks:
    # 1: 1-30
    # 2: 21-50
    # 3: 41-70
    # 4: 61-90
    # 5: 81-100
    assert len(chunks) == 5, f"Got {len(chunks)} chunks"
    
    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 30
    
    assert chunks[1]["start_line"] == 21
    assert chunks[1]["end_line"] == 50
    
    assert chunks[-1]["start_line"] == 81
    assert chunks[-1]["end_line"] == 100

def test_reconstruct_filtered():
    module = load_module()
    
    chunks = [
        {"start_line": 1, "end_line": 30, "text": "chunk1", "relevant": True},
        {"start_line": 21, "end_line": 50, "text": "chunk2", "relevant": False},
        {"start_line": 41, "end_line": 70, "text": "chunk3", "relevant": True},
    ]
    
    output = module.format_output(chunks)
    assert "chunk1" in output
    assert "chunk3" in output
    assert "chunk2" not in output
    assert "omitted" in output.lower()

def main():
    test_chunking()
    test_reconstruct_filtered()
    print("All tests passed.")

if __name__ == "__main__":
    main()
