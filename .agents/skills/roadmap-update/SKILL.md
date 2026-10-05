---
name: roadmap-update
description: >-
  Update, create, or reprioritize a product roadmap. Use when adding a new initiative and deciding what moves to make room, shifting priorities after new information comes in, moving timelines due to a dependency slip, or building a Now/Next/Later view from scratch.
argument-hint: "<update description>"
menu-description: Update, create, or reprioritize your product roadmap
---

# Roadmap Update

Use this workflow to update, create, or reprioritize a product roadmap interactively with the user.

## Usage

`/roadmap-update $ARGUMENTS`

## Workflow

### 1. Understand Current State & Context
* If a project tracker (e.g., Jira, Linear) is connected, query it to pull current roadmap items, statuses, and dates.
* If no tracker is connected, ask the user to describe, paste, or upload their current roadmap.

### 2. Determine the Operation
Ask the user for their objective and gather necessary details:
* **Add item**: Gather name, description, priority, effort, timeframe, owner, and dependencies. Suggest a fit based on capacity. **Always ask what comes off the roadmap to make room.**
* **Update status**: Options are not started, in progress, at risk, blocked, completed, cut. For blocked/at risk, demand a mitigation plan.
* **Reprioritize**: Apply standard prioritization frameworks (e.g., RICE, MoSCoW, ICE, or Value vs Effort). Ask what changed to drive this shift.
* **Move timeline**: Identify downstream impacts on dependent items and flag hard deadlines.
* **Create new**: Determine timeframe and format preference (e.g., Now/Next/Later, Quarterly Themes, OKR-aligned).

### 3. Generate Roadmap Summary
Produce a structured markdown summary including:
* **Status Overview**: X items in progress, Y completed, Z at risk.
* **Roadmap Items**: Name, status, timeframe, owner, dependencies.
* **Risks and Dependencies**: Explicitly call out cross-team dependencies and items near deadlines.
* **Changes**: If this is an update, explicitly list what was added, removed, or shifted.

### 4. Validation (Self-Check)
Before presenting the final roadmap to the user, verify:
* **Capacity**: Did we overcommit? If the roadmap has more work than a typical team can handle (assuming ~70% feature capacity), flag it.
* **Zero-Sum Constraint**: If an item was added, ensure you explicitly highlighted the tradeoff or deprioritization required.
* **Dependencies**: Ensure no item is scheduled to start *before* its explicitly listed dependencies are resolved.

### 5. Follow Up
* Offer to format the output for a specific audience (e.g., executive summary vs. engineering detail).
* If a tracker is connected, offer to apply these changes directly to the tool.
