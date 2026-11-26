"""category-v1 against a local mock of the Jev HTTP API."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

SOURCE = Path(__file__).parents[1] / "skill_router.py"
os.environ.setdefault("JEV_BIN", str(SOURCE.parent / "bin/jev"))
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("skill_router", SOURCE)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class MockJev(BaseHTTPRequestHandler):
    calls = []
    low_gate = False
    fit = 0.9
    category = {}

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(body)
        answers = {}
        for key, question in body["questions"].items():
            if question["type"] == "choice":
                names = list(question["criteria"])
                assert 1 <= len(names) <= 255
                if key == "category":
                    probabilities = {n: self.category.get(n, 0.0) for n in names}
                else:
                    probabilities = {n: float(n == names[0]) for n in names}
                choice = max(names, key=lambda n: probabilities[n])
                answers[key] = {"type": "choice", "choice": choice, "probabilities": probabilities}
            else:
                probability = 0.1 if key == "gate::prose_suffices" else 0.9
                if key.startswith("fits::"):
                    probability = self.fit
                if self.low_gate and key.startswith("gate::"):
                    probability = 1 - probability
                answers[key] = {"type": "noul", "noul": probability}
        response = json.dumps(
            {"model": "jev-latest", "answers": answers, "usage": {"input_tokens": 100}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def entry(name: str, description: str) -> dict:
    return {"name": name, "description": description, "body": "", "path": None}


ROSTER = [
    entry("my-skills:chiquita", "Cuts fluff from a doc while keeping every fact."),
    entry("superpowers:systematic-debugging", "Find the root cause before fixing."),
    entry("my-skills:addyosmani-debugging-and-error-recovery", "Systematic root-cause debugging."),
    entry("my-skills:ci-parity-run", "Run a repo's CI job list locally."),
    entry("my-skills:spec-tacular", "User-invoked spec writer."),
    entry("my-skills:addyosmani-interview-me", "Interview the user about requirements."),
]


def route(request: str, roster=ROSTER, **category) -> dict:
    MockJev.calls.clear()
    MockJev.category = category
    return router.suggest_by_category(request, roster)


def run_hook(prompt: str) -> str:
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(json.dumps({"prompt": prompt})), io.StringIO()
    try:
        router.run_prompt_hook("claude", "category-nogate-v2", "library")
        return sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = stdin, stdout


def check_hook_log() -> None:
    old_entries, old_dir = router.entries_for, os.environ.get("JEV_LOG_DIR")
    router.entries_for = lambda host, mode: ROSTER
    with tempfile.TemporaryDirectory() as raw:
        os.environ["JEV_LOG_DIR"] = raw
        try:
            MockJev.category = {"debug": 0.9}
            out = run_hook("Find why this fails; my key is ghp_abcdefghijklmnop")
            assert "superpowers:systematic-debugging" in out, out
            log = Path(raw) / "skill-router.jsonl"
            assert oct(log.stat().st_mode & 0o777) == "0o600"
            (row,) = map(json.loads, log.read_text().splitlines())
            assert "ghp_abcdefghijklmnop" not in row["prompt"], row["prompt"]
            assert row["suggestion"] == "superpowers:systematic-debugging" and row["suggestion_fit"] == 0.9
            assert row["router_version"] == "category-nogate-v2" and row["roster_mode"] == "library"
            router.entries_for = lambda host, mode: 1 / 0
            assert "failed open" in run_hook("Anything")
            assert json.loads(log.read_text().splitlines()[1])["error"] == "ZeroDivisionError"
        finally:
            router.entries_for = old_entries
            if old_dir is None:
                os.environ.pop("JEV_LOG_DIR", None)
            else:
                os.environ["JEV_LOG_DIR"] = old_dir


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockJev)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    old = {k: os.environ.get(k) for k in ("JEV_BASE_URL", "TYPESAFE_API_KEY", "JEV_ALLOW_LOCAL")}
    os.environ["JEV_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["TYPESAFE_API_KEY"] = "mock-key"
    os.environ["JEV_ALLOW_LOCAL"] = "1"
    try:
        result = route("This total is wrong; find out why.", debug=0.9, test=0.05)
        first, second = MockJev.calls
        assert set(first["questions"]) == {"category", *router.gate_questions()}
        assert "other" in first["questions"]["category"]["criteria"]
        assert set(second["questions"]["which"]["criteria"]) == {
            "superpowers:systematic-debugging",
            "my-skills:addyosmani-debugging-and-error-recovery",
        }
        assert result["suggestion"] == "superpowers:systematic-debugging", result
        assert result["requests"] == 2 and result["input_tokens"] == 200
        assert result["chosen_categories"] == ["debug"] and not result["fallback"]
        assert result["router_version"] == "category-v1"
        assert len(result["catalog_sha256"]) == 64

        result = route("Debug the flaky CI run.", debug=0.6, test=0.3)
        assert result["chosen_categories"] == ["debug", "test"]
        assert "my-skills:ci-parity-run" in result["pool"]

        result = route("Write me a PRD.", **{"plan-and-spec": 0.95})
        assert result["pool"] == ["my-skills:addyosmani-interview-me"], result["pool"]

        result = route("Hmm.", debug=0.2, test=0.2, security=0.2)
        assert result["fallback"] and result["requests"] == 3, result
        assert result["router_version"] == "category-v1"

        unknown = [*ROSTER, entry("mystery-tool", "Does something unusual.")]
        assert route("Odd task.", unknown, other=0.9)["fallback"]
        result = route("Odd task.", other=0.9)
        assert result["requests"] == 1 and result["suggestion"] is None

        MockJev.low_gate = True
        result = route("What is the capital of Iceland?", debug=0.9)
        assert result["requests"] == 1 and result["suggestion"] is None
        assert router.ROUTERS["category-v1"] is router.suggest_by_category

        nogate = router.ROUTERS["category-nogate-v2"]
        MockJev.calls.clear()
        MockJev.category = {"debug": 0.9}
        result = nogate("What is the capital of Iceland?", ROSTER)
        first, _ = MockJev.calls
        assert set(first["questions"]) == {"category"}, "no gate questions"
        fits_text = MockJev.calls[1]["questions"]["fits::superpowers:systematic-debugging"]["instructions"]
        assert "improve the execution" in fits_text, fits_text
        assert result["suggestion"] == "superpowers:systematic-debugging", result
        assert result["router_version"] == "category-nogate-v2" and result["gate"] is None
        MockJev.calls.clear()
        MockJev.category = {"other": 0.9, "debug": 0.1}
        result = nogate("What is the capital of Iceland?", ROSTER)
        assert result["requests"] == 1 and result["suggestion"] is None
        MockJev.calls.clear()
        MockJev.category = {"other": 0.3, "debug": 0.2, "test": 0.1}
        result = nogate("Hmm.", unknown)
        assert result["chosen_categories"] == ["debug", "test"] and not result["fallback"]
        assert result["requests"] == 2 and "mystery-tool" in result["pool"], result
        MockJev.fit = 0.4
        MockJev.category = {"debug": 0.9}
        assert nogate("Rename tmp in utils.py.", ROSTER)["suggestion"] is None, "below 0.55"
        MockJev.low_gate = False
        assert route("Rename tmp in utils.py.", debug=0.9)["suggestion"], "gated keeps 0.30"
        MockJev.fit = 0.9

        check_hook_log()
        print(
            "PASS: category-v1 two-request path, runner-up category, user-invoked excluded, "
            "low-confidence and uncategorized fallback, gate abstention; nogate variant"
        )
    finally:
        server.shutdown()
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
