#!/usr/bin/env python3
"""Jev AST Symbol Ranker.

Parses Python source files using standard AST, extracts symbol outlines
(functions, classes, methods), and uses a single Jev Choice request to
rank which symbol is most relevant to a query.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time


DEFAULT_MODEL = "jev-latest"
JEV = Path(os.environ.get("JEV_BIN") or Path.home() / ".local/bin/jev")


def extract_symbols(code: str) -> list[dict]:
    """Extract functions, classes, and methods from Python source code."""
    tree = ast.parse(code)
    lines = code.splitlines()
    symbols: list[dict] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            summary = doc.splitlines()[0].strip() if doc else ""
            sig = lines[node.lineno - 1].strip() if lines else node.name
            symbols.append({
                "name": node.name,
                "kind": "function",
                "signature": sig,
                "docstring": summary,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            })
        elif isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node) or ""
            class_summary = class_doc.splitlines()[0].strip() if class_doc else ""
            class_sig = lines[node.lineno - 1].strip() if lines else node.name
            symbols.append({
                "name": node.name,
                "kind": "class",
                "signature": class_sig,
                "docstring": class_summary,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            })
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(child) or ""
                    method_summary = method_doc.splitlines()[0].strip() if method_doc else ""
                    method_sig = lines[child.lineno - 1].strip() if lines else child.name
                    symbols.append({
                        "name": f"{node.name}.{child.name}",
                        "kind": "method",
                        "signature": method_sig,
                        "docstring": method_summary,
                        "start_line": child.lineno,
                        "end_line": getattr(child, "end_lineno", child.lineno),
                    })

    return symbols


def extract_symbol_source(code: str, symbol: dict) -> str:
    """Extract the exact source lines corresponding to a symbol."""
    lines = code.splitlines()
    start = max(0, symbol["start_line"] - 1)
    end = min(len(lines), symbol["end_line"])
    return "\n".join(lines[start:end])


def build_choice_questions(symbols: list[dict], query: str) -> dict:
    """Build a single Jev Choice question ranking all symbols."""
    criteria = {}
    for sym in symbols:
        summary_part = f" - {sym['docstring']}" if sym['docstring'] else ""
        criteria[sym["name"]] = f"[{sym['kind']}] {sym['signature']}{summary_part}"[:140]

    criteria["__none__"] = "None of these symbols are relevant to the query."

    return {
        "which_symbol": {
            "type": "choice",
            "instructions": (
                f"Which of these symbols/functions is most relevant to answering or "
                f"implementing the following query: {query!r}?"
            ),
            "criteria": criteria,
        }
    }


def process_ranking_response(symbols: list[dict], response: dict) -> tuple[list[dict], int]:
    """Parse Jev Choice response and order symbols by probability."""
    answers = response.get("answers", {})
    choice_answer = answers.get("which_symbol", {})
    probs = choice_answer.get("probabilities", {})
    tokens = int(response.get("usage", {}).get("input_tokens", 0))

    by_name = {s["name"]: dict(s) for s in symbols}
    ranked = []

    for name, p in sorted(probs.items(), key=lambda x: -x[1]):
        if name in by_name:
            item = by_name[name]
            item["score"] = float(p)
            ranked.append(item)

    # Append any symbols that had 0 probability or were omitted
    for sym in symbols:
        if sym["name"] not in probs and sym["name"] in by_name:
            item = by_name[sym["name"]]
            item["score"] = 0.0
            ranked.append(item)

    return ranked, tokens


def evaluate_symbols_with_jev(
    symbols: list[dict], query: str
) -> tuple[list[dict], int, float]:
    """Invoke Jev via subprocess to rank the symbols."""
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError(
            "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"
        )

    questions = build_choice_questions(symbols, query)
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    state_content = json.dumps({"query": query, "symbol_count": len(symbols)})

    start = time.perf_counter()
    process = subprocess.run(
        [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "ast_symbol_ranker"],
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
    ranked, tokens = process_ranking_response(symbols, response)
    return ranked, tokens, elapsed


def format_outline(symbols: list[dict]) -> str:
    """Format symbol outline as a readable text table."""
    rows = ["LINE RANGE   KIND        SYMBOL / SIGNATURE"]
    rows.append("-" * 65)
    for s in symbols:
        line_range = f"{s['start_line']}-{s['end_line']}".ljust(12)
        kind = s['kind'].ljust(11)
        summary = f" # {s['docstring']}" if s['docstring'] else ""
        rows.append(f"{line_range} {kind} {s['signature']}{summary}")
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Jev AST Symbol Ranker - Locate relevant code symbols via AST and Jev Choice"
    )
    parser.add_argument("file", help="Path to Python source file")
    parser.add_argument("--query", help="Goal or query to find relevant symbols for")
    parser.add_argument("--top-k", type=int, default=1, help="Number of top symbols to output (default: 1)")
    parser.add_argument("--outline-only", action="store_true", help="Print symbol outline table and exit")
    parser.add_argument("--skip-jev", action="store_true", help="Skip Jev evaluation and show outline only")

    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        code = path.read_text(encoding="utf-8")
        symbols = extract_symbols(code)
    except Exception as e:
        print(f"Error parsing {path}: {e}", file=sys.stderr)
        sys.exit(1)

    if not symbols:
        print(f"No symbols (functions or classes) found in {path}.", file=sys.stderr)
        sys.exit(0)

    if args.outline_only or args.skip_jev or not args.query:
        print(f"Discovered {len(symbols)} symbols in {path}:\n")
        print(format_outline(symbols))
        sys.exit(0)

    print(f"Extracted {len(symbols)} symbols. Evaluating with Jev...", file=sys.stderr)
    try:
        ranked, tokens, elapsed = evaluate_symbols_with_jev(symbols, args.query)
        print(f"Evaluated in {elapsed:.2f}s using {tokens} tokens.\n", file=sys.stderr)
    except Exception as e:
        print(f"Jev evaluation failed: {e}", file=sys.stderr)
        sys.exit(1)

    top_symbols = ranked[:args.top_k]
    for idx, sym in enumerate(top_symbols, 1):
        print(f"=== Rank {idx}: {sym['name']} (score: {sym.get('score', 0):.2f}, lines {sym['start_line']}-{sym['end_line']}) ===")
        print(extract_symbol_source(code, sym))
        print()


if __name__ == "__main__":
    main()
