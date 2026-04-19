# ADR-008: English system prompts, Ukrainian candidate output

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen's candidates are Ukrainian engineers; the interview must be conducted in Ukrainian. But:

- LLMs (Gemini, Claude) consistently perform better on instruction-following when the system prompt is in English.
- Prompts need to be reviewable by English-speaking engineering teams.
- The rubric, position template, and competency names exist in English in N-iX internal documentation.

Two naïve options: (a) write everything in Ukrainian, losing instruction-following quality; (b) write everything in English, making candidate experience broken. Neither is acceptable.

## Decision

Every agent system prompt has three labelled sections:

1. **ROLE / INSTRUCTIONS (English).** System behaviour, JSON schema, invariants.
2. **LEVEL PROMPTING GUIDE (English).** How to calibrate tone and question depth per candidate level (entry, specialist, expert, proficient).
3. **UKRAINIAN STYLE ANCHORS.** A block of Ukrainian exemplars that fix register, phrasing, professional-but-warm tone. Model outputs are constrained to emit candidate-facing text in Ukrainian consistent with these anchors.

Assessor agent operates **on Ukrainian candidate text**, but its JSON output uses **English field names and enum values** — this is what the Reviewer UI displays against English competency names.

## Consequences

**Positive.**
- Best-of-both-worlds: stronger instruction-following from English systems, native Ukrainian candidate experience.
- Engineering team reviews prompts in the language they work in.
- Assessor JSON is stable across language changes.

**Negative.**
- Ukrainian exemplars must be maintained — if register or tone drifts, recruiters notice.
- Model occasionally code-switches (inserts English words in Ukrainian output) — mitigated by anchors and a post-generation style check.

**Mitigation.**
- Ukrainian exemplars live in `prompts/shared/ukrainian-anchors.md` and are versioned per prompt release.
- Language-consistency test runs on every prompt change: generates N sample outputs and asserts they are monolingually Ukrainian.
