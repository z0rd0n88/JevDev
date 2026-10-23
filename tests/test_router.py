"""Local HTTP contract smoke for the Jev wrapper and router."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parents[1] / "skill_router.py"
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("skill_router", SOURCE)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class HostContracts(unittest.TestCase):
    def test_agy_benchmark_stream_and_dispatch(self):
        entries = [
            {
                "name": "test",
                "description": "authored",
                "path": "/authored/test/SKILL.md",
                "body": "test",
            }
        ]
        events = [
            {
                "event": "step_update",
                "step_update": {
                    "step_type": "tool",
                    "tool_name": "view_file",
                    "tool_info": {"args": {"AbsolutePath": entries[0]["path"]}},
                },
            },
            {"event": "result", "result": {"status": "SUCCESS"}},
        ]
        with (
            patch.object(router, "agy_roster", return_value=entries),
            patch.object(
                router.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0, stdout="\n".join(map(json.dumps, events)), stderr=""
                ),
            ) as run,
        ):
            loaded, _ = router.first_agy_skill_load(
                "Authored request", None, "pinned-test-model", entries
            )
        self.assertEqual(loaded, "test")
        self.assertEqual(run.call_args.kwargs["env"]["JEV_ROUTER_ACTIVE"], "1")
        with tempfile.TemporaryDirectory() as tmp:
            labels, output = (
                Path(tmp) / "labels.jsonl",
                Path(tmp) / "observations.jsonl",
            )
            labels.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "id": str(i),
                            "text": "authored request",
                            "gold": "test" if i == 0 else None,
                            "label_method": "blind_manual",
                            "label_reason": "authored fixture",
                        }
                    )
                    for i in range(100)
                )
            )
            with (
                patch.object(router, "host_roster", return_value=entries),
                patch.object(
                    router,
                    "suggest",
                    return_value={
                        "suggestion": "test",
                        "roster_sha256": router.roster_hash(entries),
                        "router_version": router.ROUTER_VERSION,
                    },
                ),
                patch.object(
                    router, "first_agy_skill_load", return_value=("test", 0.01)
                ) as agy,
                patch.object(router, "first_codex_skill_load") as codex,
            ):
                router.benchmark(labels, output, "pinned-test-model", "agy", limit=1)
            self.assertEqual(agy.call_count, 3)
            codex.assert_not_called()

    def test_agy_arm_rejects_changed_roster(self):
        with (
            patch.object(router, "agy_roster", return_value=[]),
            patch.object(router.subprocess, "run") as run,
        ):
            with self.assertRaises(RuntimeError):
                router.first_agy_skill_load(
                    "Authored request",
                    None,
                    "test-model",
                    [{"name": "test", "description": "test"}],
                )
            run.assert_not_called()

    def test_codex_current_and_legacy_skill_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("local", "plugin", "absolute"):
                path = root / name / "SKILL.md"
                path.parent.mkdir()
                path.write_text(
                    "---\ndescription: An authored test skill\n---\nInstructions"
                )
            prompt = (
                f"- `r0` = `{root}`\n### Available skills\n"
                "- local: A useful description (file: r0/local/SKILL.md)\n"
                "- suite:plugin: (file: r0/plugin/SKILL.md)\n"
                f"- absolute: Another description (file: {root}/absolute/SKILL.md)\n"
                "</skills_instructions>"
            )
            result = SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "role": "developer",
                            "content": [{"type": "input_text", "text": prompt}],
                        }
                    ]
                ),
            )
            with patch.object(router.subprocess, "run", return_value=result):
                entries = router.codex_roster()
            self.assertEqual(
                [e["name"] for e in entries], ["local", "suite:plugin", "absolute"]
            )

    def test_agy_active_sources_and_project_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, project = Path(tmp) / "home", Path(tmp) / "project"
            sources = [
                (home / ".gemini/antigravity-cli/skills/shared", "global"),
                (project / ".agents/skills/shared", "project"),
                (home / "enabled/skills/active", "enabled"),
                (home / "disabled/skills/hidden", "disabled"),
            ]
            for directory, body in sources:
                directory.mkdir(parents=True)
                (directory / "SKILL.md").write_text(
                    f"---\ndescription: {body}\n---\n{body}"
                )
            snapshot = {
                "status": "SUCCESS",
                "num_turns": 0,
                "command": {
                    "name": "skills",
                    "data": {
                        "skills": [
                            {
                                "name": "enabled:active",
                                "description": "enabled",
                                "path": str(home / "enabled/skills/active/SKILL.md"),
                                "model_invocable": True,
                            },
                            {
                                "name": "shared",
                                "description": "project",
                                "path": str(project / ".agents/skills/shared/SKILL.md"),
                                "model_invocable": True,
                            },
                            {
                                "name": "manual",
                                "description": "manual only",
                                "model_invocable": False,
                            },
                        ]
                    },
                },
            }
            with patch.object(
                router.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout=json.dumps(snapshot)),
            ):
                entries = router.agy_roster(project=project)
            by_name = {e["name"]: e for e in entries}
            self.assertEqual(set(by_name), {"enabled:active", "shared"})
            self.assertEqual(by_name["shared"]["description"], "project")

    def test_unknown_host_is_rejected(self):
        with self.assertRaises(ValueError):
            router.host_roster("typo")

    def test_hook_contract_for_each_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "USER_INPUT",
                        "content": "<USER_REQUEST>Fix it</USER_REQUEST>",
                    }
                )
                + "\n"
                + json.dumps(
                    {"type": "SYSTEM_MESSAGE", "content": "Authored session metadata"}
                )
                + "\n"
            )
            for host in ("claude", "codex", "agy"):
                with self.subTest(host=host):
                    event = {"cwd": tmp, "prompt": "Fix it", "model": "host-model"}
                    if host == "agy":
                        event = {
                            "workspacePaths": [tmp],
                            "transcriptPath": str(transcript),
                            "modelName": "agy-model",
                        }
                    output = io.StringIO()
                    with (
                        patch.object(
                            router.sys, "stdin", io.StringIO(json.dumps(event))
                        ),
                        patch.object(
                            router,
                            "host_roster",
                            return_value=[{"name": "test", "description": "test"}],
                        ),
                        patch.object(
                            router,
                            "suggest",
                            return_value={
                                "suggestion": "test",
                                "roster_sha256": "authored",
                            },
                        ),
                        patch.dict(
                            os.environ,
                            {"JEV_LOG_DIR": tmp, "TYPESAFE_API_KEY": "mock-key"},
                        ),
                        contextlib.redirect_stdout(output),
                    ):
                        router.run_prompt_hook(host)
                    result = json.loads(output.getvalue())
                    if host == "agy":
                        self.assertIn(
                            "test", result["injectSteps"][0]["ephemeralMessage"]
                        )
                    else:
                        self.assertEqual(
                            result["hookSpecificOutput"]["hookEventName"],
                            "UserPromptSubmit",
                        )
                    row = json.loads(
                        (Path(tmp) / "router.jsonl").read_text().splitlines()[-1]
                    )
                    self.assertEqual(row["host"], host)
                    self.assertEqual(row["roster_sha256"], "authored")

    def test_agy_does_not_route_again_after_model_or_tool_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    json.dumps(x)
                    for x in [
                        {"type": "USER_INPUT", "content": "Fix it"},
                        {"type": "PLANNER_RESPONSE", "content": "Working"},
                    ]
                )
            )
            event = {"workspacePaths": [tmp], "transcriptPath": str(transcript)}
            with (
                patch.object(router.sys, "stdin", io.StringIO(json.dumps(event))),
                patch.object(router, "host_roster") as discover,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                router.run_prompt_hook("agy")
            discover.assert_not_called()
            self.assertEqual(output.getvalue(), "")

    def test_hook_failure_never_exposes_provider_message(self):
        for host in ("claude", "codex", "agy"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                with (
                    patch.object(
                        router.sys, "stdin", io.StringIO('{"prompt": "Fix it"}')
                    ),
                    patch.object(
                        router,
                        "host_roster",
                        side_effect=RuntimeError("private-provider-body"),
                    ),
                    patch.dict(os.environ, {"JEV_LOG_DIR": tmp}),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    router.run_prompt_hook(host)
                self.assertNotIn("private-provider-body", output.getvalue())

    def test_agy_sampling_uses_typed_user_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = "Please implement the authored example workflow and verify the expected behavior."
            (root / "transcript.jsonl").write_text(
                json.dumps(
                    {
                        "type": "USER_INPUT",
                        "content": f"<USER_REQUEST>{prompt}</USER_REQUEST>",
                    }
                )
            )
            output = root / "sample.jsonl"
            router.sample_prompts(root, output, 1, "agy", 1)
            self.assertEqual(json.loads(output.read_text())["text"], prompt)


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
    result = unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(HostContracts)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockJev)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    old = {
        key: os.environ.get(key)
        for key in ("JEV_BASE_URL", "TYPESAFE_API_KEY", "JEV_ALLOW_LOCAL")
    }
    os.environ["JEV_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
    os.environ["TYPESAFE_API_KEY"] = "mock-key"
    os.environ["JEV_ALLOW_LOCAL"] = "1"
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
