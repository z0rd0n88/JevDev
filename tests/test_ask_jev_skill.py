"""Phase 6 checks: ask-jev skill text, its runnable recipes, and the Claude symlink."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).parents[1]
SKILL = ROOT / ".agents/skills/ask-jev/SKILL.md"
LINK = ROOT / ".claude/skills/ask-jev"

SYNOPSES = [
    "ask_jev_files.py files [-r] -q QUESTIONS_JSON PATH_OR_GLOB...",
    "ask_jev_files.py pick  -q QUESTION_TEXT PATH...",
    "ask_jev_files.py ask   -q QUESTIONS_JSON [--state TEXT] [--paths P...] [--command CMD]",
]
# Upstream ten-levels-of-jev tool-description.ts:14-16, including the two leading spaces.
EXAMPLES = [
    '  noul   {"type":"noul","instructions":"Is `output` a real failure rather than a flaky one?","criteria":{"true":"...","false":"..."}}  -> { noul: 0..1 }',
    '  choice {"type":"choice","instructions":"What kind of failure is `output`?","criteria":{"bug_in_code":"...","wrong_test":"...","environment":"...","other":"..."}}  -> { choice, confidence, probabilities }',
    '  score  {"type":"score","instructions":"How risky is `diff`?","criteria":["Isolated, tested","Some callers","Security sensitive, no tests"]}  -> { score, confidence, legend }',
]
OTHER_RULE = "Always give a choice an `other` option."

# Answers every question in the stub's wire shape; the live gate sees effect=read_only.
STUB = """#!/usr/bin/env python3
import json, sys
sys.stdin.read()
argv = sys.argv[1:]
qs = json.loads(argv[argv.index("-q") + 1])
out = {}
for qid, q in qs.items():
    if qid == "effect":
        out[qid] = {"type": "choice", "choice": "read_only", "confidence": 0.95, "probabilities": {"read_only": 0.9}}
    elif q["type"] == "choice":
        k = next(iter(q["criteria"]))
        out[qid] = {"type": "choice", "choice": k, "confidence": 0.8, "probabilities": {k: 0.75}}
    elif q["type"] == "score":
        out[qid] = {"type": "score", "score": 1.5}
    else:
        out[qid] = {"type": "noul", "noul": 0.1}
print(json.dumps({"model": "typesafe/jev-stub-1", "answers": out, "usage": {"input_tokens": 1}}))
"""


def text():
    return SKILL.read_text()


def frontmatter():
    m = re.match(r"---\n(.*?)\n---\n", text(), re.S)
    assert m, "no frontmatter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines())


def bash_blocks():
    return re.findall(r"```bash\n(.*?)```", text(), re.S)


def test_frontmatter_name_and_description_length():
    fm = frontmatter()
    assert fm["name"] == "ask-jev"
    assert 0 < len(fm["description"]) <= 200, len(fm["description"])


def test_synopsis_and_example_lines_are_verbatim():
    lines = text().splitlines()
    for want in SYNOPSES + EXAMPLES:
        assert want in lines, want


def test_recipes_have_no_placeholder_criteria():
    # The two upstream example lines legitimately hold "..."; recipes and rules must not.
    parts = bash_blocks() + [text().split("## Rules", 1)[1]]
    for part in parts:
        assert '"..."' not in part and "..." not in part.replace("PATH...", ""), part


def test_rules_section_has_other_option_sentence():
    assert "## Rules" in text() and OTHER_RULE in text().split("## Rules", 1)[1]


def test_three_recipes_present():
    blocks = bash_blocks()
    assert len(blocks) == 3, len(blocks)
    for block in blocks:
        assert "'" in block and block.count("'") % 2 == 0


def test_every_bash_block_runs_with_stub_and_prints_answers():
    with tempfile.TemporaryDirectory() as tmp:
        stub = Path(tmp) / "jev"
        stub.write_text(STUB)
        stub.chmod(0o755)
        env = {
            **os.environ,
            "JEV_BIN": str(stub),
            "JEV_LOG_DIR": tmp,
            "TYPESAFE_API_KEY": "stub",
        }
        for block in bash_blocks():
            script = block.replace("/home/alex/JevDev/", f"{ROOT}/")
            proc = subprocess.run(
                ["bash", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90
            )
            assert proc.returncode == 0, (block, proc.stdout, proc.stderr)
            assert "answers" in json.loads(proc.stdout), proc.stdout


def test_claude_link_is_relative_symlink():
    assert LINK.is_symlink()
    assert os.readlink(LINK) == "../../.agents/skills/ask-jev"
    assert (LINK / "SKILL.md").is_file()


def test_smoke_codex_ask_skill_prints_steps():
    out = subprocess.run(
        ["bash", str(ROOT / "smoke.sh"), "codex", "ask-skill"], capture_output=True, text=True
    ).stdout
    assert "$ask-jev" in out and "/skills" in out


def test_readme_skills_section_names_ask_jev():
    readme = (ROOT / "README.md").read_text()
    assert "ask-jev" in readme.split("## Skills", 1)[1]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok {name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    raise SystemExit(1 if failed else 0)
