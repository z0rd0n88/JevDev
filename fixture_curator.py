#!/usr/bin/env python3
"""Benchmark Fixture Curator.

Validates benchmark JSONL fixtures using deterministic checks (missing fields, duplicate IDs)
and uses Jev to flag prompts that are not self-contained or where multiple skills might be defensible.
"""

import argparse
import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import time

DEFAULT_MODEL = "jev-latest"
JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")


def validate_record(record: dict) -> list[str]:
    """Check for required fields and formatting."""
    errors = []
    required_fields = ["id", "text", "gold"]
    for field in required_fields:
        if field not in record:
            errors.append(f"Missing required field: {field}")
        elif not record[field] and record[field] is not None:
            errors.append(f"Field {field} cannot be empty")
    return errors


def find_duplicates(records: list[dict]) -> set[str]:
    """Find duplicate IDs across records."""
    counts = collections.Counter(r.get("id") for r in records if r.get("id"))
    return {id_val for id_val, count in counts.items() if count > 1}


def build_curator_questions() -> dict:
    """Build the questions for Jev."""
    return {
        "self_contained": {
            "type": "noul",
            "instructions": "Is this request self-contained enough to understand without access to external files, previous conversation turns, or specific local context? (Answer 'yes' if it makes sense on its own, 'no' if it is missing necessary context like 'fix the bug in that file' without showing the file.)"
        },
        "multiple_defensible": {
            "type": "noul",
            "instructions": "Could more than one distinct specialized agent skill be a defensible choice for satisfying this request? (Answer 'yes' if it's broad or ambiguous enough to span multiple skills, 'no' if it clearly points to only one focused approach.)"
        }
    }


def curate_with_jev(record: dict) -> dict:
    """Invoke Jev to evaluate the prompt."""
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError(
            "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"
        )
    
    state_content = f"PROMPT TEXT:\n{record.get('text', '')}"
    questions = build_curator_questions()
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    
    start = time.perf_counter()
    process = subprocess.run(
        [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "curator"],
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
    answers = response.get("answers", {})
    return {
        "self_contained": float(answers.get("self_contained", {}).get("noul", 0.0)),
        "multiple_defensible": float(answers.get("multiple_defensible", {}).get("noul", 0.0)),
        "elapsed": elapsed,
        "input_tokens": int(response.get("usage", {}).get("input_tokens", 0))
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark Fixture Curator")
    parser.add_argument("file", help="Path to the JSONL fixture file")
    parser.add_argument("--skip-jev", action="store_true", help="Only run deterministic checks")
    args = parser.parse_args()
    
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
        
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                record["_line"] = line_num
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"Line {line_num}: Invalid JSON - {e}")
                
    # Deterministic checks
    print("--- Deterministic Checks ---")
    has_errors = False
    
    dupes = find_duplicates(records)
    if dupes:
        has_errors = True
        print(f"ERROR: Found duplicate IDs: {', '.join(dupes)}")
        
    for record in records:
        errors = validate_record(record)
        if errors:
            has_errors = True
            fallback = f"Line {record.get('_line')}"
            print(f"ERROR in record {record.get('id', fallback)}:")
            for err in errors:
                print(f"  - {err}")
                
    if has_errors:
        print("\nDeterministic checks failed. Please fix these before using Jev.")
        sys.exit(1)
    else:
        print("Deterministic checks passed.")
        
    if args.skip_jev:
        print("Skipping Jev checks as requested.")
        sys.exit(0)
        
    # Jev checks
    print("\n--- Jev Curation ---")
    flagged = 0
    total_tokens = 0
    total_time = 0.0
    
    for i, record in enumerate(records, start=1):
        # We don't necessarily want to process hundreds without feedback
        print(f"Evaluating {i}/{len(records)}: {record.get('id')}...", end=" ", flush=True)
        try:
            res = curate_with_jev(record)
            total_tokens += res["input_tokens"]
            total_time += res["elapsed"]
            
            # thresholds for flags
            flags = []
            if res["self_contained"] < 0.5:
                flags.append("Not self-contained")
            if res["multiple_defensible"] >= 0.5:
                flags.append("Multiple labels defensible")
                
            if flags:
                flagged += 1
                print("FLAGGED")
                for f in flags:
                    print(f"    - {f}")
            else:
                print("OK")
                
        except Exception as e:
            print(f"ERROR: {e}")
            
    print(f"\nCompleted in {total_time:.1f}s using {total_tokens} tokens.")
    print(f"Flagged {flagged}/{len(records)} prompts for human review.")

if __name__ == "__main__":
    main()
