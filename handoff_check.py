#!/usr/bin/env python3
"""Handoff Integrity Check (Slice 1).

Compares items in a decision ledger against a handoff description.
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

def parse_ledger(content: str) -> list[str]:
    """Parse a text file into a list of ledger items (ignoring blank lines)."""
    return [line.strip() for line in content.splitlines() if line.strip()]

def load_file(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")

def build_jev_questions(items: list[str]) -> dict:
    questions = {}
    for i, item in enumerate(items):
        questions[f"item_{i}"] = {
            "type": "choice",
            "instructions": f"Evaluate this decision/constraint against the handoff text: {item!r}. Is it intact, missing, falsely complete, or changed?",
            "criteria": {
                "intact": "The handoff correctly respects and carries forward this constraint or status.",
                "missing": "The handoff drops or forgets this constraint/decision entirely.",
                "falsely_complete": "The handoff describes this item as complete, but it was actually unfinished.",
                "changed": "The constraint or next step was altered in the handoff."
            }
        }
    return questions

def evaluate_handoff(items: list[str], handoff: str) -> dict:
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError("Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY")
    
    state_content = f"HANDOFF TEXT:\n{handoff}"
    questions = build_jev_questions(items)
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    
    start = time.perf_counter()
    process = subprocess.run(
        [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "handoff_check"],
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
    results = {}
    for i in range(len(items)):
        ans = response["answers"].get(f"item_{i}", {})
        results[f"item_{i}"] = {
            "result": ans.get("choice", "error"),
            "confidence": float(ans.get("confidence", 0.0))
        }
        
    return {
        "results": results,
        "elapsed": elapsed,
        "input_tokens": int(response.get("usage", {}).get("input_tokens", 0))
    }

def main():
    parser = argparse.ArgumentParser(description="Handoff Integrity Check")
    parser.add_argument("--ledger", required=True, help="Path to the decision ledger file")
    parser.add_argument("--handoff", required=True, help="Path to the handoff text file")
    
    args = parser.parse_args()
    
    try:
        ledger_content = load_file(args.ledger)
        handoff_content = load_file(args.handoff)
        
        items = parse_ledger(ledger_content)
        if not items:
            print("Ledger is empty.")
            sys.exit(0)
            
        evaluation = evaluate_handoff(items, handoff_content)
        
        print(f"Evaluated {len(items)} items in {evaluation['elapsed']:.2f}s (Tokens: {evaluation['input_tokens']})")
        print("-" * 40)
        
        for i, item in enumerate(items):
            res = evaluation["results"][f"item_{i}"]
            verdict = res["result"].upper()
            print(f"[{verdict}] (conf: {res['confidence']:.2f}) - {item}")
            if verdict != "INTACT":
                print("  ^ WARNING: Integrity violation detected!")
                
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
