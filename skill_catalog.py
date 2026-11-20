"""Category catalog for the category-v1 skill router.

- load() reads catalog/categories.yaml and catalog/catalog.yaml and rejects unknown fields,
  categories, actions and duplicate names, so a typo fails loudly instead of hiding a skill.
- assign() gives every live-roster entry a category with its provenance: the catalog entry
  ("manual"), else a keyword rule ("rule:<hits>"), else "uncategorized".
- pools() lists the routable names per category: invoke "auto" only, including `also`.
- rank() trims a large pool by request relevance: inverse-frequency weighting with name hits
  worth 3 and description hits worth 2, after agentic-awesome-skills' outcomeDiscovery.ts.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

import yaml

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
KINDS = {"skill", "command", "agent"}
ACTIONS = {"prompt", "session", "agent"}
INVOKES = {"auto", "user", "internal"}
REASONS = {"manual", "override", "rule"}
ENTRY_FIELDS = {"name", "category", "also", "kind", "action", "invoke", "reason"}
MIN_RULE_HITS = 2
MIN_RULE_MARGIN = 1
STOP_WORDS = set(
    "a an and any are as at be by do for from how i in into is it its me my of on or our "
    "the this to use used uses using want when with without you your".split()
)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP_WORDS]


def load(directory: Path = CATALOG_DIR) -> tuple[dict, dict]:
    """Return (categories, catalog): {key: {criteria, keywords}} and {name: entry}."""
    categories = yaml.safe_load((directory / "categories.yaml").read_text())["categories"]
    if "other" not in categories:
        raise ValueError("categories.yaml needs an 'other' category")
    if not 2 <= len(categories) <= 255:
        raise ValueError("categories.yaml needs between 2 and 255 categories")
    for key, value in categories.items():
        if not str(value.get("criteria") or "").strip():
            raise ValueError(f"Category {key!r} has no criteria")
        if not isinstance(value.get("keywords"), list):
            raise ValueError(f"Category {key!r} needs a keywords list")
    document = yaml.safe_load((directory / "catalog.yaml").read_text())
    defaults = document["defaults"]
    catalog: dict[str, dict] = {}
    for source, rows in document["sources"].items():
        for row in rows:
            if set(row) - ENTRY_FIELDS:
                raise ValueError(f"Unknown catalog fields {sorted(set(row) - ENTRY_FIELDS)} in {row.get('name')!r}")
            entry = {**defaults, "also": [], **row, "source": source}
            name = entry["name"]
            if name in catalog:
                raise ValueError(f"Duplicate catalog entry {name!r}")
            for value, allowed, field in (
                (entry["kind"], KINDS, "kind"),
                (entry["action"], ACTIONS, "action"),
                (entry["invoke"], INVOKES, "invoke"),
                (entry["reason"], REASONS, "reason"),
            ):
                if value not in allowed:
                    raise ValueError(f"{name!r} has unknown {field} {value!r}")
            for category in [entry["category"], *entry["also"]]:
                if category not in categories or category == "other":
                    raise ValueError(f"{name!r} names unknown category {category!r}")
            catalog[name] = entry
    return categories, catalog


def digest(categories: dict, catalog: dict) -> str:
    """Hash of everything routing reads, recorded with each observation."""
    stable = json.dumps([categories, catalog], sort_keys=True)
    return hashlib.sha256(stable.encode()).hexdigest()


def rule_category(name: str, description: str, categories: dict) -> tuple[str | None, list[str]]:
    """Whole-token keyword vote; abstain unless one category clearly leads."""
    words = set(tokens(f"{name.replace(':', ' ')} {description}"))
    scores = sorted(
        (
            (sorted(set(value["keywords"]) & words), key)
            for key, value in categories.items()
            if key != "other"
        ),
        key=lambda pair: (-len(pair[0]), pair[1]),
    )
    (best_hits, best), (second_hits, _) = scores[0], scores[1]
    if len(best_hits) < MIN_RULE_HITS or len(best_hits) - len(second_hits) < MIN_RULE_MARGIN:
        return None, best_hits
    return best, best_hits


def assign(entries: list[dict], categories: dict, catalog: dict) -> list[dict]:
    assigned = []
    for entry in entries:
        known = catalog.get(entry["name"])
        if known:
            assigned.append(dict(known))
            continue
        category, hits = rule_category(entry["name"], entry["description"], categories)
        assigned.append(
            {
                "name": entry["name"],
                "category": category or "uncategorized",
                "also": [],
                "invoke": "auto",
                "action": "session",
                "reason": f"rule:{','.join(hits)}" if category else "uncategorized",
            }
        )
    return assigned


def pools(assigned: list[dict]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for entry in assigned:
        if entry["invoke"] != "auto":
            continue
        for category in [entry["category"], *entry["also"]]:
            grouped.setdefault(category, []).append(entry["name"])
    return grouped


def matches(term: str, words: set[str]) -> bool:
    """Exact, or a shared prefix of 4+ letters either way ("review" ~ "reviewers")."""
    return term in words or (
        len(term) >= 4
        and any(len(w) >= 4 and (w.startswith(term) or term.startswith(w)) for w in words)
    )


def rank(request: str, entries: list[dict], limit: int) -> list[dict]:
    """The `limit` entries most relevant to the request; ties keep roster order."""
    terms = set(tokens(request))
    if len(entries) <= limit or not terms:
        return entries[:limit]
    fields = [
        (set(tokens(e["name"].replace(":", " "))), set(tokens(e["description"])))
        for e in entries
    ]
    frequency = {
        t: sum(matches(t, name) or matches(t, text) for name, text in fields) for t in terms
    }

    def score(index: int) -> float:
        name, text = fields[index]
        return sum(
            (3 if matches(t, name) else 2 if matches(t, text) else 0)
            * math.log(1 + len(entries) / (1 + frequency[t]))
            for t in terms
        )

    order = sorted(range(len(entries)), key=lambda i: (-score(i), i))
    return [entries[i] for i in order[:limit]]


def coverage(entries: list[dict], categories: dict, catalog: dict) -> dict:
    assigned = assign(entries, categories, catalog)
    grouped = pools(assigned)
    live = {e["name"] for e in entries}
    return {
        "roster_skills": len(entries),
        "from_catalog": sum(e["reason"] == "manual" for e in assigned),
        "from_rule": sorted(e["name"] for e in assigned if e["reason"].startswith("rule:")),
        "uncategorized": sorted(e["name"] for e in assigned if e["category"] == "uncategorized"),
        "not_routable": sorted(e["name"] for e in assigned if e["invoke"] != "auto"),
        "catalog_entries_not_live": sorted(set(catalog) - live),
        "pool_sizes": {k: len(v) for k, v in sorted(grouped.items())},
        "catalog_sha256": digest(categories, catalog),
    }
