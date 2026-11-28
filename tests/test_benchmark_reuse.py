"""benchmark --reuse-arms copies baseline and oracle loads and reruns only the routed arm."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile

SOURCE = Path(__file__).parents[1] / "skill_router.py"
os.environ.setdefault("JEV_BIN", str(SOURCE.parent / "bin/jev"))
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("skill_router", SOURCE)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)

ROSTER = [{"name": "skill-a", "description": "A", "body": "", "path": None}]
sessions = []


def fake_route(version):
    def route(request, entries):
        return {
            "suggestion": "skill-a" if request.startswith("covered") else None,
            "requests": 1,
            "input_tokens": 10,
            "estimated_usd": 0.0,
            "seconds": 0.1,
            "roster_sha256": router.roster_hash(entries),
            "router_version": version,
        }

    return route


def fake_load(text, block, model, names):
    sessions.append(block)
    if block and "correct skill" in block:
        return "skill-a", 1.0
    return ("skill-a" if block and "skill-a" in block else None), 1.0


def expect_error(needle, **kwargs):
    try:
        router.benchmark(**kwargs)
    except ValueError as error:
        assert needle in str(error), error
        return
    raise AssertionError(f"benchmark accepted {needle!r}")


def main():
    with contextlib.redirect_stderr(io.StringIO()):
        run()
    print("PASS: reuse copies baseline and oracle, reruns routed only, refuses another roster")


def run():
    router.host_roster = lambda host: ROSTER
    router.first_claude_skill_load = fake_load
    for version in router.ROUTERS:
        router.ROUTERS[version] = fake_route(version)
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        labels = tmp / "labels.jsonl"
        labels.write_text(
            "".join(
                json.dumps(
                    {
                        "id": f"p{n:03}",
                        "host": "claude",
                        "text": f"{'covered' if n < 60 else 'uncovered'} prompt {n}",
                        "gold": "skill-a" if n < 60 else None,
                        "label_method": "blind_manual",
                        "label_reason": "authored",
                    }
                )
                + "\n"
                for n in range(100)
            )
        )
        common = {"labels_path": labels, "model": "haiku", "host": "claude"}
        first = tmp / "v2.jsonl"
        router.benchmark(output_path=first, **common)
        assert len(sessions) == 300, len(sessions)

        sessions.clear()
        second = tmp / "category.jsonl"
        result = router.benchmark(
            output_path=second, router="category-v1", reuse_path=first, **common
        )
        assert result["complete"] and len(sessions) == 100, len(sessions)
        assert all(block is None or "correct skill" not in block for block in sessions)
        rows = [json.loads(line) for line in second.read_text().splitlines()]
        before = {r["id"]: r for r in map(json.loads, first.read_text().splitlines())}
        for row in rows:
            assert row["arms_reused_from"] == "balanced-shards-v2"
            assert row["routing"]["router_version"] == "category-v1"
            for arm in ("baseline", "oracle"):
                assert row["loads"][arm] == before[row["id"]]["loads"][arm]
        assert router.score(rows)["rows_with_reused_arms"] == 100

        expect_error(
            "another observations file",
            output_path=first,
            reuse_path=first,
            **common,
        )
        router.host_roster = lambda host: [*ROSTER, {**ROSTER[0], "name": "skill-b"}]
        expect_error(
            "different host, model, or roster",
            output_path=tmp / "other.jsonl",
            router="category-v1",
            reuse_path=first,
            **common,
        )


if __name__ == "__main__":
    main()
