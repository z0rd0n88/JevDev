#!/usr/bin/env python3
"""Jev AST Symbol Ranker.

Parses Python source files using standard AST, extracts symbol outlines
(functions, classes, methods), and uses balanced Jev Choice requests to
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
SHARD_SIZE = 50


def _get_doc_summary(node: ast.AST) -> str:
    """Extract first line of docstring from an AST node."""
    doc = ast.get_docstring(node) or ""
    return doc.splitlines()[0].strip() if doc else ""


def _extract_signature(lines: list[str], node: ast.AST) -> str:
    """Extract normalized signature, supporting multi-line definitions."""
    if not lines or not hasattr(node, "lineno"):
        return getattr(node, "name", "")
    
    start_idx = max(0, node.lineno - 1)
    sig_lines = []
    
    # Scan from the def/class statement until the line ending with ':'
    for idx in range(start_idx, min(start_idx + 8, len(lines))):
        line = lines[idx].strip()
        sig_lines.append(line)
        if line.endswith(":") or "):" in line:
            break
            
    normalized = " ".join(" ".join(sig_lines).split())
    return normalized


def extract_symbols(code: str) -> list[dict]:
    """Extract functions, classes, and methods from Python source code."""
    tree = ast.parse(code)
    lines = code.splitlines()
    symbols: list[dict] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            summary = _get_doc_summary(node)
            sig = _extract_signature(lines, node)
            start_line = (
                min(node.lineno, min(d.lineno for d in node.decorator_list))
                if getattr(node, "decorator_list", None)
                else node.lineno
            )
            end_line = getattr(node, "end_lineno", None) or node.lineno
            sym_id = f"{node.name}#{start_line}"
            symbols.append({
                "id": sym_id,
                "name": node.name,
                "kind": "function",
                "signature": sig,
                "docstring": summary,
                "start_line": start_line,
                "end_line": end_line,
            })
        elif isinstance(node, ast.ClassDef):
            class_summary = _get_doc_summary(node)
            class_sig = _extract_signature(lines, node)
            class_start_line = (
                min(node.lineno, min(d.lineno for d in node.decorator_list))
                if getattr(node, "decorator_list", None)
                else node.lineno
            )
            class_end_line = getattr(node, "end_lineno", None) or node.lineno
            class_id = f"{node.name}#{class_start_line}"
            symbols.append({
                "id": class_id,
                "name": node.name,
                "kind": "class",
                "signature": class_sig,
                "docstring": class_summary,
                "start_line": class_start_line,
                "end_line": class_end_line,
            })
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_summary = _get_doc_summary(child)
                    method_sig = _extract_signature(lines, child)
                    method_start_line = (
                        min(child.lineno, min(d.lineno for d in child.decorator_list))
                        if getattr(child, "decorator_list", None)
                        else child.lineno
                    )
                    method_end_line = getattr(child, "end_lineno", None) or child.lineno
                    method_name = f"{node.name}.{child.name}"
                    method_id = f"{method_name}#{method_start_line}"
                    symbols.append({
                        "id": method_id,
                        "name": method_name,
                        "kind": "method",
                        "signature": method_sig,
                        "docstring": method_summary,
                        "start_line": method_start_line,
                        "end_line": method_end_line,
                    })

    return symbols


def extract_symbol_source(code: str, symbol: dict) -> str:
    """Extract the exact source lines corresponding to a symbol."""
    lines = code.splitlines()
    start = max(0, symbol["start_line"] - 1)
    end = min(len(lines), symbol["end_line"])
    return "\n".join(lines[start:end])


def symbol_shards(symbols: list[dict], shard_size: int = SHARD_SIZE) -> list[list[dict]]:
    """Partition symbols into near-equal balanced shards."""
    if not symbols:
        return []
    count = (len(symbols) + shard_size - 1) // shard_size
    size = (len(symbols) + count - 1) // count
    return [symbols[start : start + size] for start in range(0, len(symbols), size)]


def build_choice_questions(symbols: list[dict], query: str) -> dict:
    """Build balanced Jev Choice questions ranking all symbols."""
    questions = {}
    shards = symbol_shards(symbols)

    for shard_idx, shard in enumerate(shards):
        criteria = {}
        for sym in shard:
            summary_part = f" - {sym['docstring']}" if sym['docstring'] else ""
            sym_key = sym.get("id") or f"{sym['name']}#{sym['start_line']}"
            criteria[sym_key] = f"[{sym['kind']}] {sym['signature']}{summary_part}"[:140]

        criteria["__none__"] = "None of these symbols are relevant to the query."

        questions[f"which_symbol::{shard_idx}"] = {
            "type": "choice",
            "instructions": (
                f"Which of these symbols/functions is most relevant to answering or "
                f"implementing the following query: {query!r}?"
            ),
            "criteria": criteria,
        }

    return questions


def process_ranking_response(
    symbols: list[dict], response: dict
) -> tuple[list[dict], float, int]:
    """Parse Jev Choice response and order symbols by probability."""
    answers = response.get("answers", {})
    tokens = int(response.get("usage", {}).get("input_tokens", 0))

    by_id = {s.get("id") or f"{s['name']}#{s['start_line']}": dict(s) for s in symbols}
    scores_by_id = {}
    none_scores = []

    for key, ans in answers.items():
        if not key.startswith("which_symbol"):
            continue
        probs = ans.get("probabilities", {})
        if "__none__" in probs:
            none_scores.append(float(probs["__none__"]))
        for sym_id, p in probs.items():
            if sym_id != "__none__":
                scores_by_id[sym_id] = max(scores_by_id.get(sym_id, 0.0), float(p))

    none_score = max(none_scores, default=0.0)

    ranked = []
    for sym_id, p in sorted(scores_by_id.items(), key=lambda x: -x[1]):
        if sym_id in by_id:
            item = by_id[sym_id]
            item["score"] = p
            ranked.append(item)

    # Append any symbols that had 0 probability or were omitted
    for sym_id, item in by_id.items():
        if sym_id not in scores_by_id:
            unscored = dict(item)
            unscored["score"] = 0.0
            ranked.append(unscored)

    # Check if __none__ wins or exceeds confidence
    max_symbol_score = ranked[0]["score"] if ranked else 0.0
    if none_score > max_symbol_score or none_score >= 0.50:
        return [], none_score, tokens

    return ranked, none_score, tokens


def evaluate_symbols_with_jev(
    symbols: list[dict], query: str
) -> tuple[list[dict], float, int, float]:
    """Invoke Jev via subprocess to rank the symbols."""
    if not (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        raise RuntimeError(
            "Jev key unavailable in environment; set TYPESAFE_API_KEY or OPENROUTER_API_KEY"
        )

    questions = build_choice_questions(symbols, query)
    model = os.environ.get("JEV_MODEL") or DEFAULT_MODEL
    state_content = json.dumps({"query": query, "symbol_count": len(symbols)})

    start = time.perf_counter()
    try:
        process = subprocess.run(
            [str(JEV), "-m", model, "-q", json.dumps(questions), "-j", "ast_symbol_ranker"],
            input=state_content,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("jev timed out while evaluating symbol choice questions")
        
    elapsed = time.perf_counter() - start

    if process.returncode:
        raise RuntimeError(
            f"jev exited {process.returncode}; inspect provider access and limits locally"
        )

    response = json.loads(process.stdout)
    ranked, none_score, tokens = process_ranking_response(symbols, response)
    return ranked, none_score, tokens, elapsed


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
        ranked, none_score, tokens, elapsed = evaluate_symbols_with_jev(symbols, args.query)
        print(f"Evaluated in {elapsed:.2f}s using {tokens} tokens.\n", file=sys.stderr)
    except Exception as e:
        print(f"Jev evaluation failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not ranked:
        print(f"No relevant symbols found for query {args.query!r} (None/abstain score: {none_score:.2f}).")
        sys.exit(0)

    top_symbols = ranked[:args.top_k]
    for idx, sym in enumerate(top_symbols, 1):
        print(f"=== Rank {idx}: {sym['name']} (score: {sym.get('score', 0):.2f}, lines {sym['start_line']}-{sym['end_line']}) ===")
        print(extract_symbol_source(code, sym))
        print()


if __name__ == "__main__":
    main()
