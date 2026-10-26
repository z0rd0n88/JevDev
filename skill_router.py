#!/usr/bin/env python3
"""Local, reproducible prototype of the TypeSafe two-request skill router.

Only a single request's text is sent to Jev. Claude transcript files are never
sent to either API by this program.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml

from jev_patterns import call, input_tokens, model_name

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
ROUTER_VERSION = "balanced-shards-v2"
WIDE_LIMIT = 60
SHORTLIST = 3
SHARD_SIZE = 255
EXCERPT = 700
GATE_THRESHOLD = 0.30
FITS_THRESHOLD = 0.30
PRICE_PER_MILLION_INPUT = 0.042
GATES = {
    "acts_on_user_system": "Is the assistant being asked to act on the user's files, accounts, devices, or online services, rather than only to explain or advise?",
    "would_follow_documented_procedure": "Would a careful expert answering this consult a specific documented procedure or set of commands, rather than answering from general understanding?",
    "prose_suffices": "Could a knowledgeable generalist fully satisfy this request in prose, with no tools, no documentation, and no access to the user's files or accounts?",
}


def skill_entry(name: str, path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"Missing frontmatter: {path}")
    _, front, body = content.split("---", 2)
    metadata = yaml.safe_load(front)
    description = " ".join(str(metadata["description"]).split())
    return {
        "name": name,
        "description": description,
        "body": body.strip(),
        "path": str(path),
    }


def live_skill_names(config: Path) -> list[str]:
    command = [
        "claude",
        "-p",
        "Say OK.",
        "--model",
        "haiku",
        "--tools",
        "Skill",
        "--allowedTools",
        "Skill",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--max-turns",
        "1",
        "--max-budget-usd",
        "0.10",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    process = subprocess.run(
        command, cwd=config, capture_output=True, text=True, timeout=40, check=False
    )
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event["skills"]
    raise RuntimeError(
        f"Claude Code returned no system init skill listing (exit {process.returncode})"
    )


def plugin_installations() -> list[dict]:
    process = subprocess.run(
        ["claude", "plugin", "list", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if process.returncode:
        raise RuntimeError("Could not list Claude Code plugins")
    return json.loads(process.stdout)


def roster(config: Path = CONFIG) -> list[dict]:
    names = live_skill_names(config)
    candidates: dict[str, dict] = {}
    for path in (config / "skills").glob("*/SKILL.md"):
        candidates[path.parent.name] = skill_entry(path.parent.name, path)
    # The live list is authoritative. Disk only supplies descriptions; disabled
    # caches cannot enter the roster merely because a SKILL.md exists there.
    installs = sorted(plugin_installations(), key=lambda entry: not entry["enabled"])
    for plugin in installs:
        base = Path(plugin["installPath"])
        prefix = plugin["id"].split("@", 1)[0]
        for path in base.rglob("SKILL.md"):
            name = f"{prefix}:{path.parent.name}"
            if name in names and name not in candidates:
                candidates[name] = skill_entry(name, path)
        for path in base.glob("commands/**/*.md"):
            name = f"{prefix}:{path.stem}"
            if name not in names or name in candidates:
                continue
            content = path.read_text(encoding="utf-8")
            front = (
                yaml.safe_load(content.split("---", 2)[1])
                if content.startswith("---\n")
                else {}
            )
            description = " ".join(
                str((front or {}).get("description") or name.replace(":", " ")).split()
            )
            candidates[name] = {
                "name": name,
                "description": description,
                "body": content[:1000],
                "path": str(path),
            }
    entries = []
    for name in names:
        entries.append(
            candidates.get(name)
            or {
                "name": name,
                "description": f"Claude Code built-in command: {name.replace('-', ' ')}",
                "body": "",
                "path": None,
            }
        )
    if len(names) != len(set(names)):
        raise ValueError("Duplicate names in live skill listing")
    return entries


def codex_roster() -> list[dict]:
    """Read the model-visible Codex skill listing and resolve its file aliases."""
    process = subprocess.run(
        ["codex", "debug", "prompt-input", "Skill roster snapshot."],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={
            **os.environ,
            "RAYON_NUM_THREADS": os.environ.get("RAYON_NUM_THREADS") or "1",
        },
    )
    if process.returncode:
        raise RuntimeError("Could not capture Codex model-visible prompt input")
    messages = json.loads(process.stdout)
    prompt = "\n".join(
        block.get("text", "")
        for message in messages
        if message.get("role") == "developer"
        for block in message.get("content", [])
        if block.get("type") == "input_text"
    )
    roots = dict(re.findall(r"- `(?P<alias>r\d+)` = `(?P<path>[^`]+)`", prompt))
    if "### Available skills" not in prompt:
        raise RuntimeError("Codex prompt contains no Available skills section")
    listing = prompt.split("### Available skills", 1)[1].split(
        "</skills_instructions>", 1
    )[0]
    rows = re.findall(r"^- (.+?): \(file: (r\d+/[^)]+)\)", listing, re.MULTILINE)
    entries: dict[str, dict] = {}
    for name, aliased_path in rows:
        alias, relative = aliased_path.split("/", 1)
        if alias not in roots:
            raise ValueError(f"Unknown Codex skill root: {alias}")
        path = Path(roots[alias]) / relative
        entries.setdefault(name, skill_entry(name, path))
    if not entries:
        raise RuntimeError("Codex prompt skill listing was empty")
    return list(entries.values())


def host_roster(host: str) -> list[dict]:
    return roster() if host == "claude" else codex_roster()


def index_text(entries: list[dict]) -> str:
    return "\n".join(f"- {x['name']}: {x['description'][:WIDE_LIMIT]}" for x in entries)


def skill_shards(entries: list[dict]) -> list[list[dict]]:
    """Split into near-equal Choices without exceeding Jev's option limit."""
    if not entries:
        raise ValueError("Cannot route an empty skill roster")
    count = (len(entries) + SHARD_SIZE - 1) // SHARD_SIZE
    size = (len(entries) + count - 1) // count
    return [entries[start : start + size] for start in range(0, len(entries), size)]


def wide_questions(entries: list[dict]) -> dict:
    questions = {}
    for shard_number, shard in enumerate(skill_shards(entries)):
        questions[f"which::{shard_number}"] = {
            "type": "choice",
            "instructions": "Which of these skills, if any, is the right one to load to help with the user's latest request?",
            "criteria": {x["name"]: x["description"][:WIDE_LIMIT] for x in shard},
        }
    questions.update(
        {
            f"gate::{key}": {"type": "noul", "instructions": text}
            for key, text in GATES.items()
        }
    )
    return questions


def roster_hash(entries: list[dict]) -> str:
    stable = [{"name": x["name"], "description": x["description"]} for x in entries]
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def inspect_roster(entries: list[dict]) -> dict:
    shards = skill_shards(entries)
    payload = index_text(entries).encode("utf-8")
    state = {"request": "x" * 1000, "recent_context": ""}
    questions = wide_questions(entries)
    wide = json.dumps(
        {"state": state, "questions": questions},
        ensure_ascii=False,
    ).encode("utf-8")
    longest = max(
        len(
            json.dumps(
                {"state": state, "question": question}, ensure_ascii=False
            ).encode("utf-8")
        )
        for question in questions.values()
    )
    return {
        "skills": len(entries),
        "local_skills": sum(":" not in x["name"] for x in entries),
        "enabled_plugin_skills": sum(":" in x["name"] for x in entries),
        "choice_option_limit": 255,
        "choice_shards": len(shards),
        "largest_shard": max(map(len, shards)),
        "router_version": ROUTER_VERSION,
        "descriptions_from_fallback": sum(x["path"] is None for x in entries),
        "index_utf8_bytes": len(payload),
        "wide_request_utf8_bytes_with_1000_char_prompt": len(wide),
        "max_state_plus_question_utf8_bytes": longest,
        "index_sha256": hashlib.sha256(payload).hexdigest(),
        "roster_sha256": roster_hash(entries),
        "byte_upper_bound_under_64k": len(wide) < 65536,
        "longest_question_bound_under_32k": longest < 32768,
        "note": "Jev's exact tokenizer is unavailable locally. The UTF-8 byte count bounds all wide questions plus a 1000-character ASCII prompt; each Choice is smaller than the full request. Capture provider-reported tokens in a live run.",
    }


def jev(questions: dict, request: str) -> tuple[dict, float]:
    response = call({"request": request, "recent_context": ""}, questions, job="routing")
    return response, response["elapsed"]


def suggest(request: str, entries: list[dict]) -> dict:
    by_name = {x["name"]: x for x in entries}
    first, first_seconds = jev(wide_questions(entries), request)
    answers = first["answers"]
    ranked = []
    for shard_number, _ in enumerate(skill_shards(entries)):
        probabilities = answers[f"which::{shard_number}"]["probabilities"]
        ranked.extend(
            sorted(probabilities.items(), key=lambda pair: (-pair[1], pair[0]))[
                :SHORTLIST
            ]
        )
    gate_values = {key: float(answers[f"gate::{key}"]["noul"]) for key in GATES}
    gate = sum(
        1 - value if key == "prose_suffices" else value
        for key, value in gate_values.items()
    ) / len(GATES)
    result = {
        "suggestion": None,
        "model": first.get("model") or model_name(),
        "shard_shortlist": ranked,
        "gate": gate,
        "gate_values": gate_values,
        "fits": {},
        "requests": 1,
        "seconds": first_seconds,
        "input_tokens": input_tokens(first),
        "roster_sha256": roster_hash(entries),
        "router_version": ROUTER_VERSION,
    }
    if gate < GATE_THRESHOLD:
        result["estimated_usd"] = (
            result["input_tokens"] * PRICE_PER_MILLION_INPUT / 1_000_000
        )
        return result
    names = [name for name, _ in ranked]
    second_questions = {
        "which": {
            "type": "choice",
            "instructions": "Exactly one of these skills is the right one to load for the user's latest request. Which one? Read what each actually does, not just its name.",
            "criteria": {
                name: f"{by_name[name]['description']} — {by_name[name]['body'][:EXCERPT]}"
                for name in names
            },
        }
    }
    second_questions.update(
        {
            f"fits::{name}": {
                "type": "noul",
                "instructions": f"Does the skill {name!r} do the specific thing the user's request asks for? It is described as: {by_name[name]['description']}",
            }
            for name in names
        }
    )
    second, second_seconds = jev(second_questions, request)
    fits = {name: float(second["answers"][f"fits::{name}"]["noul"]) for name in names}
    chosen = second["answers"]["which"]["choice"]
    result.update(
        {
            "suggestion": chosen if fits.get(chosen, 0.0) >= FITS_THRESHOLD else None,
            "fits": fits,
            "requests": 2,
            "seconds": first_seconds + second_seconds,
            "input_tokens": result["input_tokens"] + input_tokens(second),
        }
    )
    result["estimated_usd"] = (
        result["input_tokens"] * PRICE_PER_MILLION_INPUT / 1_000_000
    )
    return result


def score(rows: list[dict]) -> dict:
    """Score *observed first loads*, never silently replace them with gold."""
    if len(rows) < 100:
        raise ValueError("At least 100 labeled prompts are required")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate prompt IDs")
    covered = [row for row in rows if row.get("gold")]
    uncovered = [row for row in rows if row.get("gold") is None]
    if not covered or not uncovered:
        raise ValueError("Both covered and uncovered prompts are required")
    if any(row.get("label_method") != "blind_manual" for row in rows):
        raise ValueError("Every gold label must declare blind_manual provenance")
    if any(not row.get("label_reason") for row in rows):
        raise ValueError("Every gold label needs a brief independent label_reason")
    report = {
        "prompts": len(rows),
        "covered": len(covered),
        "uncovered": len(uncovered),
    }
    hosts = {row.get("host") for row in rows}
    if len(hosts) > 1:
        raise ValueError("Score one host at a time")
    report["host"] = next(iter(hosts))
    roster_hashes = {(row.get("routing") or {}).get("roster_sha256") for row in rows}
    if len(roster_hashes) != 1:
        raise ValueError("Observations span multiple roster snapshots")
    report["roster_sha256"] = next(iter(roster_hashes))
    router_versions = {(row.get("routing") or {}).get("router_version") for row in rows}
    if len(router_versions) != 1 or None in router_versions:
        raise ValueError("Observations need one recorded router version")
    report["router_version"] = next(iter(router_versions))
    history = [row for row in rows if "historical_first_load" in row]
    if history:
        report["gold_vs_historical_disagreements"] = sum(
            row["gold"] != row["historical_first_load"] for row in history
        )
        report["historical_comparisons"] = len(history)
    for arm in ("baseline", "routed", "oracle"):
        if any(arm not in row.get("loads", {}) for row in rows):
            raise ValueError(f"Missing observed first load for {arm}")
        wrong = sum(row["loads"][arm] != row["gold"] for row in covered)
        needless = sum(row["loads"][arm] is not None for row in uncovered)
        report[arm] = {
            "wrong_loads": wrong,
            "wrong_load_rate": wrong / len(covered),
            "needless_loads": needless,
            "needless_load_rate": needless / len(uncovered),
        }
    routed = [row.get("routing") for row in rows]
    if any(value is None for value in routed):
        raise ValueError("Missing measured Jev routing record")
    report["jev"] = {
        "requests": sum(value["requests"] for value in routed),
        "input_tokens": sum(value["input_tokens"] for value in routed),
        "estimated_usd": sum(value["estimated_usd"] for value in routed),
        "mean_added_seconds": sum(value["seconds"] for value in routed) / len(rows),
    }
    if all("arm_seconds" in row for row in rows):
        report["mean_routed_minus_baseline_agent_seconds"] = sum(
            row["arm_seconds"]["routed"] - row["arm_seconds"]["baseline"]
            for row in rows
        ) / len(rows)
    return report


def first_claude_skill_load(
    prompt: str,
    suggestion: str | None,
    model: str,
    expected_names: set[str] | None = None,
) -> tuple[str | None, float]:
    command = [
        "claude",
        "-p",
        "--model",
        model,
        "--tools",
        "Skill",
        "--allowedTools",
        "Skill",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--max-turns",
        "1",
        "--max-budget-usd",
        "0.10",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if suggestion is not None:
        command.extend(["--append-system-prompt", suggestion])
    start = time.perf_counter()
    process = subprocess.run(
        command,
        input=prompt,
        cwd=CONFIG,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    elapsed = time.perf_counter() - start
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            if (
                expected_names is not None
                and set(event.get("skills", [])) != expected_names
            ):
                raise RuntimeError(
                    "Claude agent arm has a different live skill roster from its router"
                )
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                return block.get("input", {}).get("skill"), elapsed
    if process.returncode:
        raise RuntimeError(
            f"claude arm exited {process.returncode} without a Skill call; inspect auth locally"
        )
    return None, elapsed


def first_codex_skill_load(
    prompt: str, suggestion: str | None, model: str, entries: list[dict]
) -> tuple[str | None, float]:
    # Codex CLI has no append-system-prompt flag. Its suggestion is appended as
    # a delimited user-message block, so this arm is not prompt-identical to
    # Claude's and must be reported separately.
    if suggestion:
        prompt = f"{prompt}\n\n{suggestion}"
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--json",
        "--model",
        model,
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--cd",
        str(PROJECT_ROOT),
        "-",
    ]
    start = time.perf_counter()
    process = subprocess.run(
        command,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env={
            **os.environ,
            "RAYON_NUM_THREADS": os.environ.get("RAYON_NUM_THREADS") or "1",
        },
    )
    elapsed = time.perf_counter() - start
    paths = [(x["path"], x["name"]) for x in entries if x["path"]]
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.started":
            continue
        item = event.get("item") or {}
        if item.get("type") != "command_execution":
            continue
        command_text = item.get("command") or ""
        matches = [
            (command_text.index(path), name)
            for path, name in paths
            if path in command_text
        ]
        if matches:
            return min(matches)[1], elapsed
    if process.returncode:
        raise RuntimeError(
            f"codex arm exited {process.returncode} without a skill read"
        )
    return None, elapsed


def suggestion_block(name: str | None, oracle: bool = False) -> str:
    if name:
        lead = (
            "The correct skill for this evaluation request is"
            if oracle
            else "Relevant to the current request:"
        )
        body = f"{lead} {name}. Ignore this if it does not fit what the user actually asked for."
    else:
        body = "No skill in the roster appears relevant to this request."
    return f"<skill_relevance>\n{body}\n</skill_relevance>"


def sample_prompts(
    transcripts: Path, output: Path, count: int, host: str, per_session: int
) -> dict:
    """Extract candidate user turns without exposing past Skill calls to labelers."""
    if per_session < 1:
        raise ValueError("--per-session must be at least 1")
    candidates = {}
    for path in transcripts.rglob("*.jsonl"):
        try:
            accepted = 0
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if host == "claude":
                        if event.get("type") != "user" or event.get("isSidechain"):
                            continue
                        content = event.get("message", {}).get("content", "")
                    else:
                        payload = event.get("payload") or {}
                        if (
                            event.get("type") != "response_item"
                            or payload.get("role") != "user"
                        ):
                            continue
                        content = payload.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            block.get("text", "")
                            for block in content
                            if isinstance(block, dict)
                            and block.get("type") in ("text", "input_text")
                        )
                    if not isinstance(content, str):
                        continue
                    prompt = " ".join(content.split())
                    if not 50 <= len(prompt) <= 1000 or prompt.startswith(
                        ("<", "(", "{", "/")
                    ):
                        continue
                    if prompt.startswith("Skill /") or re.match(
                        r"^Invoke the `[^`]+` skill", prompt
                    ):
                        continue
                    if re.search(
                        r"(?i)(api.?key|password|secret|token|BEGIN |[a-f0-9]{32}|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b)",
                        prompt,
                    ):
                        continue
                    identifier = hashlib.sha256(prompt.encode()).hexdigest()[:16]
                    candidates[identifier] = {"id": identifier, "text": prompt}
                    accepted += 1
                    if accepted >= per_session:
                        break
        except OSError:
            continue
    selected = sorted(
        candidates.values(),
        key=lambda row: hashlib.sha256((row["id"] + "sample-v1").encode()).hexdigest(),
    )[:count]
    with output.open("w", encoding="utf-8") as stream:
        for row in selected:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "eligible_prompts": len(candidates),
        "sampled": len(selected),
        "output": str(output),
    }


def save_observations(path: Path, rows: dict[str, dict]) -> None:
    """Atomically checkpoint completed work and any in-progress prompt."""
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows.values():
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def benchmark(
    labels_path: Path,
    output_path: Path,
    model: str,
    host: str,
    limit: int | None = None,
) -> dict:
    labels = [
        json.loads(line)
        for line in labels_path.read_text().splitlines()
        if line.strip()
    ]
    if len(labels) < 100:
        raise ValueError("The labeled set must contain at least 100 prompts")
    labels_by_id = {row["id"]: row for row in labels}
    if len(labels_by_id) != len(labels):
        raise ValueError("The labeled set contains duplicate prompt IDs")
    if any(row.get("label_method") != "blind_manual" for row in labels):
        raise ValueError("Labels must be prepared without viewing historical loads")
    if any(not row.get("label_reason") for row in labels):
        raise ValueError("Every label needs a brief independent label_reason")
    if any(row.get("host") not in (None, host) for row in labels):
        raise ValueError("Label file is for a different host")
    if not any(row.get("gold") is None for row in labels):
        raise ValueError("The labeled set needs uncovered prompts")
    entries = host_roster(host)
    names = {x["name"] for x in entries}
    if any(row.get("gold") not in names | {None} for row in labels):
        raise ValueError("A gold skill is absent from the current roster")
    existing = {}
    if output_path.exists():
        existing = {
            row["id"]: row
            for line in output_path.read_text().splitlines()
            if line.strip()
            for row in [json.loads(line)]
        }
    if set(existing) - set(labels_by_id):
        raise ValueError("Existing observations contain IDs absent from labels")
    if any(
        (row["text"], row["gold"])
        != (labels_by_id[identifier]["text"], labels_by_id[identifier]["gold"])
        for identifier, row in existing.items()
    ):
        raise ValueError("Existing observations disagree with the label file")
    expected_hash = roster_hash(entries)
    if any(
        row.get("host") != host
        or row.get("agent_model") != model
        or (row.get("routing") or {}).get("roster_sha256") != expected_hash
        or (row.get("routing") or {}).get("router_version") != ROUTER_VERSION
        for row in existing.values()
    ):
        raise ValueError(
            "Existing observations use a different host, model, roster, or router version"
        )
    done = 0
    for row in labels:
        if limit is not None and done >= limit:
            break
        observed = existing.get(row["id"])
        if observed and all(
            arm in observed.get("loads", {}) for arm in ("baseline", "routed", "oracle")
        ):
            continue
        if observed is None:
            routing = suggest(row["text"], entries)
            observed = {
                **row,
                "routing": routing,
                "loads": {},
                "arm_seconds": {},
                "agent_model": model,
                "host": host,
            }
            existing[row["id"]] = observed
            save_observations(output_path, existing)
        for arm, block in (
            ("baseline", None),
            ("routed", suggestion_block(observed["routing"]["suggestion"])),
            ("oracle", suggestion_block(row["gold"], oracle=True)),
        ):
            if arm in observed["loads"]:
                continue
            if host == "claude":
                loaded, seconds = first_claude_skill_load(
                    row["text"], block, model, names
                )
            else:
                loaded, seconds = first_codex_skill_load(
                    row["text"], block, model, entries
                )
            observed["loads"][arm] = loaded
            observed["arm_seconds"][arm] = seconds
            save_observations(output_path, existing)
            print(
                f"{host} {row['id']} {arm}: {loaded or '-'} ({seconds:.1f}s)",
                file=sys.stderr,
                flush=True,
            )
        done += 1
    return {
        "newly_completed": done,
        "output": str(output_path),
        "complete": len(existing) == len(labels)
        and all(
            all(arm in row.get("loads", {}) for arm in ("baseline", "routed", "oracle"))
            for row in existing.values()
        ),
    }


def run_prompt_hook(host: str) -> None:
    """Route a host UserPromptSubmit event and return a non-blocking hint."""
    try:
        event = json.load(sys.stdin)
        prompt = event.get("prompt") if isinstance(event, dict) else None
        if not isinstance(prompt, str) or not prompt.strip():
            return
        routing = suggest(prompt, host_roster(host))
        suggestion = routing.get("suggestion")
        if not suggestion:
            return
        context = (
            f"Jev skill router suggests `{suggestion}` for this request. "
            "Load that skill and use its instructions if it fits the task."
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    }
                }
            )
        )
    except Exception:
        # Routing is advisory: a Jev outage or missing key must never block a prompt.
        message = (
            "Jev skill routing failed open; this prompt will continue without a "
            "router suggestion. Check the Jev credentials and router configuration."
        )
        print(json.dumps({"systemMessage": message}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude", "codex"), default="claude")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("measure")
    route = sub.add_parser("route")
    route.add_argument("request")
    sub.add_parser("hook", help="handle a host UserPromptSubmit event from stdin")
    grade = sub.add_parser("score")
    grade.add_argument(
        "observations", type=Path, help="JSONL with id, gold, loads, routing"
    )
    run = sub.add_parser("benchmark")
    run.add_argument("labels", type=Path)
    run.add_argument("observations", type=Path)
    run.add_argument("--model", default=None)
    run.add_argument("--limit", type=int, default=None)
    sample = sub.add_parser("sample")
    sample.add_argument("output", type=Path)
    sample.add_argument("--transcripts", type=Path, default=None)
    sample.add_argument("--count", type=int, default=300)
    sample.add_argument("--per-session", type=int, default=3)
    args = parser.parse_args()
    if args.command == "hook":
        run_prompt_hook(args.host)
        return
    if args.command == "sample":
        transcript_dir = args.transcripts or (
            CONFIG / "projects" if args.host == "claude" else CODEX_HOME / "sessions"
        )
        print(
            json.dumps(
                sample_prompts(
                    transcript_dir,
                    args.output,
                    args.count,
                    args.host,
                    args.per_session,
                ),
                indent=2,
            )
        )
        return
    if args.command == "score":
        rows = [
            json.loads(line)
            for line in args.observations.read_text().splitlines()
            if line.strip()
        ]
        print(json.dumps(score(rows), indent=2, sort_keys=True))
        return
    if args.command == "benchmark":
        model = args.model or ("haiku" if args.host == "claude" else "gpt-6-luna")
        print(
            json.dumps(
                benchmark(args.labels, args.observations, model, args.host, args.limit),
                indent=2,
            )
        )
        return
    entries = host_roster(args.host)
    if args.command == "measure":
        print(json.dumps(inspect_roster(entries), indent=2, sort_keys=True))
    elif args.command == "route":
        print(json.dumps(suggest(args.request, entries), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, KeyError) as error:
        print(f"skill_router: {error}", file=sys.stderr)
        sys.exit(2)
