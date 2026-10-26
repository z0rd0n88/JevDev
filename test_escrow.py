#!/usr/bin/env python3
"""Test Intent Escrow (Slice 1).

Judges whether an edited assertion still protects the previously stated behavior.
"""

import argparse
from pathlib import Path
import sys

from jev_patterns import call, input_tokens

def load_diff_file(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Diff file not found: {path}")
    return path.read_text(encoding="utf-8")

def build_jev_questions() -> dict:
    return {
        "intent": {
            "type": "choice",
            "instructions": "Evaluate the test modification in the diff. Does the edited assertion still protect the original intent and behavior, or has it been weakened to allow incorrect behavior to pass?",
            "criteria": {
                "protects": "The edited test still enforces the original required behavior (e.g., it was refactored for readability or new APIs, but is logically equivalent).",
                "weakened": "The edited test removes, skips, or softens an assertion, allowing behavior to pass that should have failed.",
                "unrelated": "The change only affects setup/teardown, unrelated logging, or is not modifying an assertion."
            }
        }
    }

def evaluate_test_escrow(diff: str) -> dict:
    response = call(f"TEST DIFF:\n{diff}", build_jev_questions(), job="test_escrow")
    intent = response["answers"]["intent"]
    return {
        "result": intent["choice"],
        "confidence": float(intent.get("confidence", 0.0)),
        "elapsed": response["elapsed"],
        "input_tokens": input_tokens(response),
    }

def main():
    parser = argparse.ArgumentParser(description="Test Intent Escrow")
    parser.add_argument("--diff", required=True, help="Path to the test diff file")
    
    args = parser.parse_args()
    
    try:
        diff_content = load_diff_file(args.diff)
        result = evaluate_test_escrow(diff_content)
        
        print(f"Diff Size: {len(diff_content)} bytes")
        print(f"Verdict:   {result['result'].upper()} (confidence {result['confidence']:.2f})")
        print(f"Time:      {result['elapsed']:.2f}s | Tokens: {result['input_tokens']}")
        
        if result["result"] == "weakened":
            print("\nWARNING: Test intent appears to be WEAKENED. Human review required!")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
