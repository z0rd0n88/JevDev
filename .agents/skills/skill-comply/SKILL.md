---
name: skill-comply
description: >-
  Audits an existing skill against the latest Antigravity customization guidelines. Use when the user asks to review, audit, or check a skill for compliance with best practices or characteristics.
argument-hint: "<skill-name or path>"
menu-description: Audit a skill against latest Antigravity best practices
---

# Skill Compliance Audit (skill-comply)

Use this workflow to evaluate an existing skill against the official Antigravity customization guidelines, ensuring it is optimized for agent execution.

## Usage

`/skill-comply $ARGUMENTS`

## Workflow

### 1. Fetch Latest Guidance (Required)
Before analyzing the target skill, you MUST read the official built-in guidelines to ensure you are auditing against the most current standard.
* Execute a tool call to read `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/skills.md`.
* Focus specifically on the "Best Practices for Writing Skills" section (e.g., Progressive Disclosure, Executable Helpers, Validation Steps, No Duplication) and frontmatter requirements.

### 2. Read the Target Skill
* Locate the target skill based on the user's input (usually found in `.agents/skills/<name>/SKILL.md` or `~/.gemini/config/skills/<name>/SKILL.md`).
* Read its `SKILL.md` file and explore its directory structure to see if it uses subdirectories like `scripts/` or `references/`.

### 3. Evaluate Compliance
Compare the target skill against the official guidance. Assess the following dimensions:
* **Trigger Specificity**: Does the frontmatter `description` clearly explain *what* it does and exactly *when* the agent should invoke it in the third person?
* **Progressive Disclosure**: Is the core `SKILL.md` concise? Are bulky resources, prompts, or extensive documentation pushed out to a `references/` folder?
* **No Duplication (Token Efficiency)**: Does the skill waste tokens teaching the agent standard coding practices, generic frameworks (e.g., how Git works), or things an LLM inherently knows?
* **Executable Helpers**: If the skill involves complex terminal commands, are they encapsulated in a `scripts/` directory, or are they bloated into the markdown?
* **Self-Validating**: Does the skill include explicit instructions on how the agent should verify its own work (e.g., checking logs, running dry-runs, self-audits) before concluding?

### 4. Generate Audit Report
Present a structured markdown report to the user:
* **Summary**: A one-sentence verdict on the skill's overall health.
* **Compliance Checklist**: A bulleted list of the official best practices, marked as Pass/Fail/Partial, with a brief explanation of *why* based on the file contents.
* **Recommended Fixes**: Specific, actionable steps to bring the skill into compliance.

### 5. Remediation
* Ask the user if they would like you to automatically execute the recommended fixes (e.g., rewriting `SKILL.md`, extracting content to `references/`, or generating helper scripts).
