#!/usr/bin/env python3
"""Jev Smart Reader.

Reads a file, chunks it, and uses Jev to filter out irrelevant chunks based on a user query.
This reduces the token cost of injecting large files into an LLM's context.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

DEFAULT_MODEL = "jev-latest"
JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")


def chunk_text(text: str, chunk_size: int = 50, overlap: int = 10) -> list[dict]:
    """Split text into overlapping chunks."""
    lines = text.splitlines()
    chunks = []
    i = 0
    while i < len(lines):
        start = i
        end = min(i + chunk_size, len(lines))
        chunks.append({
            "start_line": start + 1,
            "end_line": end,
            "text": "\n".join(lines[start:end]),
            "relevant": None  # To be filled by Jev
        })
        if end == len(lines):
            break
        i += (chunk_size - overlap)
    return chunks


def build_jev_questions(query: str) -> dict:
    """Build the noul question for Jev."""
    return {
        "relevant": {
            "type": "noul",
            "instructions": f"Is this snippet of text relevant to answering the following query: {query!r}? Answer 'yes' if it contains helpful context, 'no' if it is completely irrelevant."
        }
    }


def evaluate_chunk(chunk: dict, questions: dict) -> dict:
    """Invoke Jev to evaluate a single chunk."""
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError(
            "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"
        )
    
    state_content = f"SNIPPET:\n{chunk['text']}"
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    
    process = subprocess.run(
        [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "smart_reader"],
        input=state_content,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    
    if process.returncode:
        raise RuntimeError(f"jev exited {process.returncode}; {process.stderr}")
        
    response = json.loads(process.stdout)
    answers = response.get("answers", {})
    return {
        "score": float(answers.get("relevant", {}).get("noul", 0.0)),
        "input_tokens": int(response.get("usage", {}).get("input_tokens", 0))
    }


def format_output(chunks: list[dict]) -> str:
    """Stitch relevant chunks together, leaving placeholders for omitted text."""
    output = []
    last_end = 0
    
    for chunk in chunks:
        if not chunk.get("relevant"):
            continue
            
        # If there's a gap between the last printed line and this chunk's start
        if chunk["start_line"] > last_end + 1 and last_end != 0:
            output.append(f"\n... [lines {last_end + 1}-{chunk['start_line'] - 1} omitted] ...\n")
            
        # We only want to print the part of the chunk we haven't printed yet
        lines = chunk["text"].splitlines()
        
        start_idx = 0
        if last_end >= chunk["start_line"]:
            start_idx = last_end - chunk["start_line"] + 1
            
        if start_idx < len(lines):
            output.append("\n".join(lines[start_idx:]))
            last_end = chunk["end_line"]
            
    if not output:
        return "No relevant sections found."
        
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Jev Smart Reader - Filter files for relevance")
    parser.add_argument("file", help="Path to the file to read")
    parser.add_argument("--query", required=True, help="The goal or query to filter by")
    parser.add_argument("--chunk-size", type=int, default=50, help="Lines per chunk")
    parser.add_argument("--overlap", type=int, default=10, help="Line overlap between chunks")
    parser.add_argument("--threshold", type=float, default=0.5, help="Confidence threshold (0.0 to 1.0)")
    
    args = parser.parse_args()
    
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
        
    text = path.read_text(encoding="utf-8")
    chunks = chunk_text(text, chunk_size=args.chunk_size, overlap=args.overlap)
    
    print(f"File split into {len(chunks)} chunks.", file=sys.stderr)
    
    questions = build_jev_questions(args.query)
    total_tokens = 0
    
    for i, chunk in enumerate(chunks, 1):
        print(f"Evaluating chunk {i}/{len(chunks)}...", file=sys.stderr, end=" ", flush=True)
        try:
            res = evaluate_chunk(chunk, questions)
            total_tokens += res["input_tokens"]
            chunk["relevant"] = res["score"] >= args.threshold
            print(f"{'RELEVANT' if chunk['relevant'] else 'OMITTED'} (score: {res['score']:.2f})", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            chunk["relevant"] = True  # Default to keep on error
            
    print(f"\n--- FILTERED OUTPUT (Used {total_tokens} tokens) ---\n", file=sys.stderr)
    print(format_output(chunks))


if __name__ == "__main__":
    main()
