"""Library mode: catalog entries resolve to files, hints carry paths, a Read of one is a load."""

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
catalog_module = router.skill_catalog


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def entry(name, source, kind="skill", invoke="auto"):
    bare = name.split(":", 1)[1] if name.startswith("agent:") else name
    return {"name": bare, "source": source, "kind": kind, "invoke": invoke, "category": "debug", "also": []}


def check_resolution(tmp: Path) -> dict:
    write(tmp / "mine/skills/fix-it/SKILL.md", "---\nname: fix-it\ndescription: Find  the root cause.\n---\nBody text.")
    write(tmp / "cache/ThinkTime/1.0/skills/idea/SKILL.md", "no frontmatter at all")
    write(tmp / "agents/debugger.md", "---\ndescription: Debugs things.\n---\nAgent body.")
    write(tmp / "mine/skills/hidden/SKILL.md", "---\ndescription: user only\n---\n")
    library_file = write(
        tmp / "library.yaml",
        "sources:\n"
        f"  my-skills:\n    - {tmp}/elsewhere/{{skill}}/SKILL.md\n    - {tmp}/mine/skills/{{skill}}/SKILL.md\n"
        f"  local-plugins:\n    - {tmp}/cache/{{plugin}}/*/skills/{{skill}}/SKILL.md\n"
        f"  agents-parked:\n    - {tmp}/agents/{{skill}}.md\n",
    )
    catalog = {
        "my-skills:fix-it": entry("my-skills:fix-it", "my-skills"),
        "my-skills:hidden": entry("my-skills:hidden", "my-skills", invoke="user"),
        "my-skills:gone": entry("my-skills:gone", "my-skills"),
        "ThinkTime:idea": entry("ThinkTime:idea", "local-plugins"),
        "agent:debugger": entry("agent:debugger", "agents-parked", kind="agent"),
        "cloud:thing": entry("cloud:thing", "cloud-synced"),
    }
    entries, missing = catalog_module.library(catalog, library_file)
    by_name = {e["name"]: e for e in entries}
    assert set(by_name) == {"my-skills:fix-it", "ThinkTime:idea", "agent:debugger"}, by_name
    assert missing == ["my-skills:gone"], missing
    assert by_name["my-skills:fix-it"]["description"] == "Find the root cause."
    assert by_name["my-skills:fix-it"]["body"] == "Body text."
    assert by_name["ThinkTime:idea"]["description"] == "idea"
    assert by_name["agent:debugger"]["kind"] == "agent"
    return by_name


def check_hints_and_parsing(by_name: dict) -> None:
    skill, agent = by_name["my-skills:fix-it"], by_name["agent:debugger"]
    block = router.suggestion_block(skill["name"], path=skill["path"])
    assert f"Its instructions are at {skill['path']}; read that file" in block, block
    assert "run its instructions as a subagent" in router.suggestion_block(agent["name"], path=agent["path"])
    assert "my-skills:fix-it." in router.suggestion_block("my-skills:fix-it")
    paths = {e["path"]: e["name"] for e in by_name.values()}

    def stream(*reads, skills=()):
        lines = [json.dumps({"type": "system", "subtype": "init", "skills": list(skills)})]
        content = [{"type": "tool_use", "name": "Read", "input": {"file_path": r}} for r in reads]
        lines.append(json.dumps({"type": "assistant", "message": {"content": content}}))
        return "\n".join(lines)

    assert router.parse_library_load(stream("/tmp", skill["path"]), paths) == "my-skills:fix-it"
    assert router.parse_library_load(stream("/tmp/guess/SKILL.md"), paths) is None
    try:
        router.parse_library_load(stream(skill["path"], skills=["live-skill"]), paths)
    except RuntimeError as error:
        assert "lists live skills" in str(error)
    else:
        raise AssertionError("a live roster in a library arm must be refused")


def check_benchmark(tmp: Path, by_name: dict) -> None:
    entries = list(by_name.values())
    blocks = []
    router.entries_for = lambda host, mode: entries
    router.ROUTERS["category-v1"] = lambda request, roster: {
        "suggestion": "my-skills:fix-it" if request.startswith("covered") else None,
        "requests": 1,
        "input_tokens": 1,
        "estimated_usd": 0.0,
        "seconds": 0.0,
        "roster_sha256": router.roster_hash(roster),
        "router_version": "category-v1",
    }

    def fake_load(text, block, model, paths):
        blocks.append(block)
        target = next((p for p in paths if block and p in block), None)
        return (paths[target] if target else None), 0.5

    router.first_claude_library_load = fake_load
    labels = write(
        tmp / "labels.jsonl",
        "".join(
            json.dumps(
                {
                    "id": f"p{n:03}",
                    "host": "claude",
                    "text": f"{'covered' if n < 60 else 'uncovered'} {n}",
                    "gold": "my-skills:fix-it" if n < 60 else None,
                    "label_method": "blind_manual",
                    "label_reason": "authored",
                }
            )
            + "\n"
            for n in range(100)
        ),
    )
    output = tmp / "obs.jsonl"
    with contextlib.redirect_stderr(io.StringIO()):
        result = router.benchmark(
            labels, output, "haiku", "claude", router="category-v1", roster_mode="library"
        )
    assert result["complete"] and len(blocks) == 300
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert all(r["roster_mode"] == "library" for r in rows)
    assert rows[0]["loads"] == {"baseline": None, "routed": "my-skills:fix-it", "oracle": "my-skills:fix-it"}
    assert sum(by_name["my-skills:fix-it"]["path"] in (b or "") for b in blocks) == 120
    try:
        router.benchmark(labels, tmp / "codex.jsonl", "m", "codex", roster_mode="library")
    except ValueError as error:
        assert "Claude host only" in str(error)
    else:
        raise AssertionError("library mode must refuse the Codex host")
    try:
        router.benchmark(labels, output, "haiku", "claude", router="category-v1")
    except ValueError as error:
        assert "different host, model, roster" in str(error)
    else:
        raise AssertionError("a live run must not resume library observations")


def main():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        by_name = check_resolution(tmp)
        check_hints_and_parsing(by_name)
        check_benchmark(tmp, by_name)
    print("PASS: library resolution and misses, path hints, Read-as-load parsing, library benchmark")


if __name__ == "__main__":
    main()
