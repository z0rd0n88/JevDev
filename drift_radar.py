#!/usr/bin/env python3
"""Decision Drift Radar (Slice 1).

Compares a recorded owner decision with a PR diff hunk to judge whether
the change implements, contradicts, or leaves the decision unaddressed.
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
    """Load the contents of a diff file."""
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Diff file not found: {path}")
    return path.read_text(encoding="utf-8")

def build_jev_questions() -> dict:
    return {
        "drift": {
            "type": "choice",
            "instructions": "Compare the recorded owner decision with the PR diff hunk. Does the change implement the decision, contradict it, leave it unaddressed, or intentionally defer an explicitly deferred value?",
            "criteria": {
                "implements": "The change correctly fulfills the owner's decision.",
                "contradicts": "The change directly goes against the owner's stated decision.",
                "unaddressed": "The change fails to address the owner's decision entirely, despite being relevant.",
                "defers": "The change fills in or addresses a value/feature that the owner explicitly decided to defer to later."
            }
        }
    }

def evaluate_drift(decision: str, diff: str) -> dict:
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError("Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY")
    
    state_content = f"OWNER DECISION:\n{decision}\n\nDIFF HUNK:\n{diff}"
    questions = build_jev_questions()
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    
    start = time.perf_counter()
    process = subprocess.run(
        [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "drift_radar"],
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
        "result": response["answers"]["drift"]["choice"],
        "confidence": float(response["answers"]["drift"].get("confidence", 0.0)),
        "elapsed": elapsed,
        "input_tokens": int(response.get("usage", {}).get("input_tokens", 0))
    }

def main():
    parser = argparse.ArgumentParser(description="Decision Drift Radar")
    parser.add_argument("--decision", required=True, help="The recorded owner decision text")
    parser.add_argument("--diff", required=True, help="Path to the diff file")
    
    args = parser.parse_args()
    
    try:
        diff_content = load_diff_file(args.diff)
        result = evaluate_drift(args.decision, diff_content)
        
        print(f"Decision: {args.decision}")
        print(f"Diff Size: {len(diff_content)} bytes")
        print(f"Verdict:  {result['result'].upper()} (confidence {result['confidence']:.2f})")
        print(f"Time:     {result['elapsed']:.2f}s | Tokens: {result['input_tokens']}")
        
        if result["result"] in ("contradicts", "unaddressed"):
            print("\nWARNING: Review required! Drift detected.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
