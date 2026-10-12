# Architectural Post-Mortem: Jev Smart Reader (Decommissioned)

**Date:** 2026-10-12  
**Status:** Decommissioned (Tier 3 Kill)  
**Reference Issue:** [#18](https://github.com/z0rd0n88/JevDev/issues/18)  
**Prior Prototype:** `smart_reader.py` (PR #11)

---

## 1. Executive Summary

`smart_reader.py` was prototyped to reduce token costs when coding agents inject large source files into LLM contexts. It split files into 50-line overlapping chunks, evaluated each chunk sequentially with Jev (`noul` yes/no relevance classifier), and stitched only the relevant chunks together.

Following the prototype portfolio refinement (`/agent-skills:idea-refine`), the feature was evaluated as an **anti-pattern** and designated **Tier 3 (Kill)**. The implementation files (`smart_reader.py` and `tests/test_smart_reader.py`) have been removed from the repository.

---

## 2. Core Drivers for Decommissioning

### 1. Economic Inversion
- Evaluating a 1,000-line file requires 25 sequential Jev API calls.
- At ~200 input tokens per call, that consumes 5,000 provider tokens and 25 round-trips (~30–50 seconds).
- By contrast, modern LLM context windows (Claude 3.5 Sonnet, Gemini 1.5/2.0, GPT-4o) handle 1,000 lines (~3,000 tokens) in a single request in <1 second for fractions of a cent.
- The pre-filter cost exceeded the cost of the raw context injection it was designed to prevent.

### 2. Syntactic Decapitation
- Blind line-based slicing (50 lines with 10-line overlap) routinely bisects functions, classes, and syntactic blocks.
- Output chunks joined with `... [lines X-Y omitted] ...` break AST syntax and strip crucial imports, type signatures, and local definitions needed for agent reasoning.

### 3. Solved Problem
- Fast, deterministic tools (`ripgrep`, `ctags`, tree-sitter, language server protocols) locate symbols and relevant code in milliseconds with zero token overhead and zero hallucination risk.

---

## 3. Alternative Recommended Patterns

If context reduction is revisited in the future, avoid line-level LLM chunking in favor of:
1. **Deterministic AST Symbol Slicing:** Parse file structure via `tree-sitter` or `ctags` to extract outline signatures, then evaluate symbol relevance at the definition level.
2. **Deterministic Search First:** Rely on Ripgrep/LSP queries for code discovery before injecting target files into the agent context.
