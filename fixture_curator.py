#!/usr/bin/env python3
"""Benchmark Fixture Curator.

Validates benchmark JSONL fixtures using deterministic checks (missing fields, duplicate IDs)
and uses Jev to flag prompts that are not self-contained or where multiple skills might be defensible.
"""

import argparse
import collections
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

DEFAULT_MODEL = "jev-latest"
JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")


def validate_record(record: dict) -> list[str]:
    """Check required fields and their types: id and text are non-empty strings, gold is a string or null."""
    if not isinstance(record, dict):
        return ["Record is not a JSON object"]
    errors = []
    for field in ("id", "text", "gold"):
        if field not in record:
            errors.append(f"Missing required field: {field}")
            continue
        value = record[field]
        if field == "gold" and value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Field {field} must be a non-empty string")
    return errors


def find_duplicates(records: list[dict]) -> set[str]:
    """Find duplicate IDs across records."""
    counts = collections.Counter(r.get("id") for r in records if isinstance(r.get("id"), str))
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


def score(answers: dict, key: str) -> float:
    """Strict noul read: a missing, non-numeric, NaN or out-of-range score is an error, never a verdict."""
    value = answers[key]["noul"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
        raise ValueError(f"invalid {key} score: {value!r}")
    return float(value)


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
        # Do not echo stderr: provider error bodies can include the request text.
        raise RuntimeError(f"jev exited {process.returncode}; inspect provider access and limits locally")

    response = json.loads(process.stdout)
    answers = response["answers"]  # strict: a missing answer is an error, never a 0.0 verdict
    return {
        "self_contained": score(answers, "self_contained"),
        "multiple_defensible": score(answers, "multiple_defensible"),
        "elapsed": elapsed,
        "input_tokens": int((response.get("usage") or {}).get("input_tokens") or 0),
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark Fixture Curator")
    parser.add_argument("file", help="Path to the JSONL fixture file")
    parser.add_argument("--skip-jev", action="store_true", help="Only run deterministic checks")
    args = parser.parse_args()
    
    path = Path(args.file)
    records = []
    has_errors = False
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (ValueError, RecursionError) as e:
                    has_errors = True
                    print(f"ERROR: Line {line_num}: Invalid JSON - {e}")
                    continue
                if not isinstance(record, dict):
                    has_errors = True
                    print(f"ERROR: Line {line_num}: Record is not a JSON object")
                    continue
                record["_line"] = line_num
                records.append(record)
    except (OSError, UnicodeDecodeError) as e:
        print(f"Cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Deterministic checks
    print("--- Deterministic Checks ---")
    if not records:
        has_errors = True
        print("ERROR: No records found")

    dupes = find_duplicates(records)
    if dupes:
        has_errors = True
        print(f"ERROR: Found duplicate IDs: {', '.join(sorted(dupes))}")

    for record in records:
        errors = validate_record(record)
        if errors:
            has_errors = True
            print(f"ERROR in record at line {record['_line']}:")
            for err in errors:
                print(f"  - {err}")

    if has_errors:
        print("\nDeterministic checks failed. Please fix these before using Jev.")
        sys.exit(1)
    print("Deterministic checks passed.")

    if args.skip_jev:
        print("Skipping Jev checks as requested.")
        sys.exit(0)

    # Jev checks
    print("\n--- Jev Curation ---")
    flagged = 0
    failed = 0
    total_tokens = 0
    total_time = 0.0

    for i, record in enumerate(records, start=1):
        print(f"Evaluating {i}/{len(records)}: {record['id']}...", end=" ", flush=True)
        try:
            res = curate_with_jev(record)
        except Exception as e:
            failed += 1
            print(f"ERROR: {type(e).__name__}: {e}")
            continue
        total_tokens += res["input_tokens"]
        total_time += res["elapsed"]

        # ponytail: uncalibrated 0.5 thresholds; set them from human-reviewed flags.
        flags = []
        if res["self_contained"] < 0.5:
            flags.append("Not self-contained")
        # Ambiguity is only meaningful for prompts that carry a skill label.
        if record["gold"] is not None and res["multiple_defensible"] >= 0.5:
            flags.append("Multiple labels defensible")

        if flags:
            flagged += 1
            print("FLAGGED")
            for f in flags:
                print(f"    - {f}")
        else:
            print("OK")

    print(f"\nCompleted in {total_time:.1f}s using {total_tokens} tokens.")
    print(f"Flagged {flagged}/{len(records)} prompts for human review; {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
