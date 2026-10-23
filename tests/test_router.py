"""Local HTTP contract smoke for the Jev wrapper and router."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import threading


SOURCE = Path(__file__).parents[1] / "skill_router.py"
spec = importlib.util.spec_from_file_location("skill_router", SOURCE)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class MockJev(BaseHTTPRequestHandler):
    calls = []
    low_gate = False

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        assert self.path == "/v1/systemone", self.path
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(body)
        answers = {}
        for key, question in body["questions"].items():
            if question["type"] == "choice":
                names = list(question["criteria"])
                assert 1 <= len(names) <= 255
                answers[key] = {
                    "type": "choice",
                    "choice": names[0],
                    "probabilities": {
                        name: (1.0 if name == names[0] else 0.0) for name in names
                    },
                }
            else:
                probability = 0.1 if key == "gate::prose_suffices" else 0.9
                if self.low_gate:
                    probability = 0.9 if key == "gate::prose_suffices" else 0.1
                answers[key] = {"type": "noul", "noul": probability}
        response = json.dumps(
            {"model": "jev-latest", "answers": answers, "usage": {"input_tokens": 111}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockJev)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    old = {key: os.environ.get(key) for key in ("JEV_BASE_URL", "JEV_ALLOW_LOCAL", "TYPESAFE_API_KEY")}
    os.environ["JEV_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["JEV_ALLOW_LOCAL"] = "1"  # jev sends a loopback route no key, and only with this opt-in
    os.environ["TYPESAFE_API_KEY"] = "mock-key"
    try:
        entries = [
            {
                "name": f"skill-{number:03}",
                "description": "Example skill",
                "body": "Example body",
                "path": None,
            }
            for number in range(260)
        ]
        result = router.suggest("Help me with this workflow", entries)
        assert result["suggestion"] == "skill-000", result
        assert result["requests"] == 2
        assert result["input_tokens"] == 222
        assert len(MockJev.calls) == 2
        assert len(MockJev.calls[0]["questions"]["which::0"]["criteria"]) == 130
        assert len(MockJev.calls[0]["questions"]["which::1"]["criteria"]) == 130
        assert [len(shard) for shard in router.skill_shards(entries[:256])] == [
            128,
            128,
        ]
        assert MockJev.calls[0]["state"]["request"] == "Help me with this workflow"
        assert MockJev.calls[0]["model"] == "jev-latest"
        MockJev.calls.clear()
        MockJev.low_gate = True
        result = router.suggest("What does this mean?", entries)
        assert result["suggestion"] is None
        assert result["requests"] == 1
        assert len(MockJev.calls) == 1
        print(
            "PASS: HTTP contract, balanced Choice sharding, two-request path, one-request abstention"
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
