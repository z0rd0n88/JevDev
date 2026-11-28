"""The shipped catalog loads, covers every category, and assigns with provenance."""

import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parents[1]))

import skill_catalog  # noqa: E402


def entry(name: str, description: str = "") -> dict:
    return {"name": name, "description": description, "body": "", "path": None}


def expect_error(directory: Path, needle: str) -> None:
    try:
        skill_catalog.load(directory)
    except ValueError as error:
        assert needle in str(error), error
        return
    raise AssertionError(f"load() accepted a catalog that should fail: {needle}")


def main():
    categories, catalog = skill_catalog.load()
    assert len(catalog) >= 473, len(catalog)
    assert "other" in categories
    every = skill_catalog.pools(
        skill_catalog.assign(
            [entry(name) for name in catalog], categories, catalog
        )
    )
    assert set(every) == set(categories) - {"other"}, set(categories) - set(every)
    assert "zord-workflow:spec-tacular" not in every["plan-and-spec"]
    assert "agent:shepherd:lens" not in every["review-and-audit"]
    assert "agent:debugger" in every["debug"]
    assert "security-review" not in every["security"]  # skillOverrides off
    assert catalog["code-tour"]["kind"] == "skill" and catalog["agent:code-tour"]["kind"] == "agent"
    labels = Path(__file__).parents[1] / "benchmarks/pilot-labels-claude-2026-11.jsonl"
    for row in map(json.loads, labels.read_text().splitlines()):
        gold = row["gold"]
        assert gold is None or catalog[gold]["invoke"] == "auto", gold
        for alternative in row.get("alternatives", []):
            key = alternative
            assert catalog[key]["invoke"] == "auto", alternative
    assert "superpowers:test-driven-development" in every["debug"]

    assert skill_catalog.rule_category(
        "ledger-helper", "Chase invoices and prep payroll for the business", categories
    )[0] == "business"
    assert skill_catalog.rule_category("x", "Fix a bug", categories)[0] is None
    assigned = skill_catalog.assign(
        [entry("zord-workflow:chiquita", "debug failing errors"), entry("mystery", "nothing to see")],
        categories,
        catalog,
    )
    assert [(a["category"], a["reason"]) for a in assigned] == [
        ("writing-and-communication", "manual"),
        ("uncategorized", "uncategorized"),
    ]

    pool = [
        entry("upstash:upstash-redis-js", "Redis SDK for caches and sessions"),
        entry("upstash:upstash-ratelimit-js", "Rate limiting for APIs with Redis"),
        entry("upstash:upstash-vector-js", "Vector database for embeddings"),
    ]
    assert skill_catalog.rank("add rate limiting to my login API", pool, 1)[0][
        "name"
    ] == "upstash:upstash-ratelimit-js"
    assert skill_catalog.rank("anything", pool, 5) == pool

    report = skill_catalog.coverage(
        [entry("zord-workflow:chiquita"), entry("mystery")], categories, catalog
    )
    assert report["from_catalog"] == 1 and report["uncategorized"] == ["mystery"]
    assert "ClaudesMods:prd" in report["catalog_entries_not_live"]

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        for name in ("categories.yaml", "catalog.yaml"):
            shutil.copy(skill_catalog.CATALOG_DIR / name, directory / name)
        original = (directory / "catalog.yaml").read_text()
        for broken, needle in (
            ("    - {name: chiquita, category: writing-and-communication}\n" * 2, "Duplicate"),
            ("    - {name: zz, category: nowhere}\n", "unknown category"),
            ("    - {name: zz, category: other}\n", "unknown category"),
            ("    - {name: zz, category: debug, colour: red}\n", "Unknown catalog fields"),
            ("    - {name: zz, category: debug, action: launch}\n", "unknown action"),
            ("    - {name: zz, category: debug, invoke: off}\n", "unknown invoke False"),
            ("    - {name: zz, category: debug, kind: agent, projects: [friendex]}\n", "owner/repo"),
        ):
            (directory / "catalog.yaml").write_text(
                original.replace("  my-skills:\n", "  my-skills:\n" + broken, 1)
            )
            expect_error(directory, needle)
    print("PASS: catalog loads, every category routable, provenance, rule abstain, rank, validation")


if __name__ == "__main__":
    main()
