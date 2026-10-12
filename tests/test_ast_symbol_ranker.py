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

    def test_build_choice_question(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        questions = ast_symbol_ranker.build_choice_questions(symbols, "how to connect to database?")
        
        self.assertIn("which_symbol", questions)
        q = questions["which_symbol"]
        self.assertEqual(q["type"], "choice")
        self.assertIn("criteria", q)
        self.assertIn("connect_db", q["criteria"])
        self.assertIn("__none__", q["criteria"])

    def test_rank_symbols_mock(self):
        symbols = ast_symbol_ranker.extract_symbols(SAMPLE_CODE)
        mock_response = {
            "answers": {
                "which_symbol": {
                    "probabilities": {
                        "connect_db": 0.88,
                        "UserManager.find_user_by_email": 0.08,
                        "format_report": 0.02,
                        "UserManager": 0.01,
                        "UserManager.__init__": 0.01,
                        "__none__": 0.00
                    }
                }
            },
            "usage": {"input_tokens": 350}
        }
        
        ranked, tokens = ast_symbol_ranker.process_ranking_response(symbols, mock_response)
        self.assertEqual(tokens, 350)
        self.assertEqual(ranked[0]["name"], "connect_db")
        self.assertAlmostEqual(ranked[0]["score"], 0.88)


if __name__ == "__main__":
    unittest.main()
