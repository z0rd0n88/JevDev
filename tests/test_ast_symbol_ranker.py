#!/usr/bin/env python3
"""Tests for AST Symbol Ranker."""

import sys
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import ast_symbol_ranker


SAMPLE_CODE = """\"\"\"Sample module.\"\"\"

import os

def connect_db(host: str, port: int = 5432):
    \"\"\"Establish connection to the database.\"\"\"
    return f"connected to {host}:{port}"

class UserManager:
    \"\"\"Manages user operations.\"\"\"

    def __init__(self, db_client):
        self.db = db_client

    def find_user_by_email(self, email: str) -> dict:
        \"\"\"Lookup a user by their email address.\"\"\"
        return {"email": email}

def format_report(data: dict) -> str:
    \"\"\"Format data into markdown report.\"\"\"
    return str(data)
"""

DECORATED_AND_MULTILINE_CODE = """\"\"\"Advanced module.\"\"\"

@property
def user_id(self) -> int:
    \"\"\"User unique identifier.\"\"\"
    return self._id

@decorator_a
@decorator_b(flag=True)
def complex_query(
    user_id: int,
    start_date: str,
    end_date: str = "2026-12-31"
) -> list[dict]:
    \"\"\"Run a complex query spanning multiple dates.\"\"\"
    return []
"""


class TestASTSymbolRanker(unittest.TestCase):

    def test_extract_symbols(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        names = [s["name"] for s in symbols]
        
        self.assertIn("connect_db", names)
        self.assertIn("UserManager", names)
        self.assertIn("UserManager.__init__", names)
        self.assertIn("UserManager.find_user_by_email", names)
        self.assertIn("format_report", names)
        
        # Check metadata for connect_db
        db_sym = next(s for s in symbols if s["name"] == "connect_db")
        self.assertEqual(db_sym["kind"], "function")
        self.assertEqual(db_sym["docstring"], "Establish connection to the database.")
        self.assertTrue(db_sym["start_line"] > 0)
        self.assertTrue(db_sym["end_line"] >= db_sym["start_line"])
        self.assertIn("connect_db", db_sym["signature"])

    def test_extract_symbols_empty_file(self):
        symbols = ast_symbol_ranker.extract_symbols("# only comments\nimport sys\n")
        self.assertEqual(symbols, [])

    def test_extract_symbols_syntax_error(self):
        with self.assertRaises(SyntaxError):
            ast_symbol_ranker.extract_symbols("def broken(:")

    def test_extract_symbol_source(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        db_sym = next(s for s in symbols if s["name"] == "connect_db")
        source = ast_symbol_ranker.extract_symbol_source(SAMPLE_CODE, db_sym)
        self.assertIn("def connect_db", source)
        self.assertIn("return f\"connected to {host}:{port}\"", source)
        self.assertNotIn("UserManager", source)

    def test_decorated_function_includes_decorators_in_source(self):
        symbols = ast_symbol_ranker.extract_symbols(DECORATED_AND_MULTILINE_CODE)
        cq = next(s for s in symbols if s["name"] == "complex_query")
        source = ast_symbol_ranker.extract_symbol_source(DECORATED_AND_MULTILINE_CODE, cq)
        
        # Must include both decorators
        self.assertIn("@decorator_a", source)
        self.assertIn("@decorator_b(flag=True)", source)
        self.assertIn("def complex_query(", source)

    def test_multiline_signature_captured(self):
        symbols = ast_symbol_ranker.extract_symbols(DECORATED_AND_MULTILINE_CODE)
        cq = next(s for s in symbols if s["name"] == "complex_query")
        sig = cq["signature"]
        
        # Multi-line signature should contain parameters and return type
        self.assertIn("user_id: int", sig)
        self.assertIn("start_date: str", sig)
        self.assertIn("-> list[dict]:", sig)

    def test_build_choice_question(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        questions = ast_symbol_ranker.build_choice_questions(symbols, "how to connect to database?")
        
        self.assertIn("which_symbol::0", questions)
        q = questions["which_symbol::0"]
        self.assertEqual(q["type"], "choice")
        self.assertIn("criteria", q)
        # Unique IDs are used for criteria
        criteria_keys = list(q["criteria"].keys())
        self.assertTrue(any(k.startswith("connect_db#") for k in criteria_keys))
        self.assertIn("__none__", q["criteria"])

    def test_rank_symbols_mock(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        connect_id = f"connect_db#{symbols[0]['start_line']}"
        mock_response = {
            "answers": {
                "which_symbol::0": {
                    "probabilities": {
                        connect_id: 0.88,
                        "__none__": 0.05
                    }
                }
            },
            "usage": {"input_tokens": 350}
        }
        
        ranked, none_score, tokens = ast_symbol_ranker.process_ranking_response(symbols, mock_response)
        self.assertEqual(tokens, 350)
        self.assertEqual(ranked[0]["name"], "connect_db")
        self.assertAlmostEqual(ranked[0]["score"], 0.88)
        self.assertAlmostEqual(none_score, 0.05)

    def test_rank_symbols_none_wins(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        connect_id = f"connect_db#{symbols[0]['start_line']}"
        mock_response = {
            "answers": {
                "which_symbol::0": {
                    "probabilities": {
                        "__none__": 0.95,
                        connect_id: 0.05
                    }
                }
            },
            "usage": {"input_tokens": 350}
        }
        
        ranked, none_score, tokens = ast_symbol_ranker.process_ranking_response(symbols, mock_response)
        self.assertEqual(ranked, [])
        self.assertAlmostEqual(none_score, 0.95)

    def test_large_symbol_count_sharding(self):
        # Create 70 synthetic symbols
        large_symbols = [
            {
                "id": f"func_{i}#{i*3}",
                "name": f"func_{i}",
                "kind": "function",
                "signature": f"def func_{i}():",
                "docstring": f"Function {i}",
                "start_line": i * 3,
                "end_line": i * 3 + 2,
            }
            for i in range(70)
        ]
        questions = ast_symbol_ranker.build_choice_questions(large_symbols, "query")
        # Should be sharded across multiple Choice questions
        self.assertTrue(len(questions) > 1)
        for key in questions:
            self.assertTrue(key.startswith("which_symbol::"))
            self.assertIn("__none__", questions[key]["criteria"])


if __name__ == "__main__":
    unittest.main()
