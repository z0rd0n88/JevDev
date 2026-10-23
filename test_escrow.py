#!/usr/bin/env python3
"""Test Intent Escrow (Slice 1).

Judges whether an edited assertion still protects the previously stated behavior.
"""

import argparse
from pathlib import Path
import sys

import json
import os
import subprocess
import time

DEFAULT_MODEL = "jev-latest"
JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")

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
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError("Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY")
    
    state_content = f"TEST DIFF:\n{diff}"
    questions = build_jev_questions()
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    
    start = time.perf_counter()
    process = subprocess.run(
        [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "test_escrow"],
        input=state_content,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    elapsed = time.perf_counter() - start
    
    if process.returncode:
        raise RuntimeError(f"jev exited {process.returncode}; {process.stderr}")
        
    response = json.loads(process.stdout)
    return {
        "result": response["answers"]["intent"]["choice"],
        "confidence": float(response["answers"]["intent"].get("confidence", 0.0)),
        "elapsed": elapsed,
        "input_tokens": int(response.get("usage", {}).get("input_tokens", 0))
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
