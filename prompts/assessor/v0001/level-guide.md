# Assessor — level prompting guide — v0001

Levels are defined by the rubric node's explicit L1–L4 descriptors. This guide tells you how to *interpret* those descriptors consistently.

---

## The four levels

Each rubric node provides four level descriptors (L1 – L4). Treat them as the authoritative definition for that node. This guide adds only meta-rules for how to map evidence to the descriptors.

### Level 1 — Entry

- Recognition without depth. Can name the thing; cannot yet operate it autonomously.
- Example evidence: "I know about database indexes — they make queries faster."
- Mapping: if the candidate demonstrates awareness and basic correct naming but no trade-off reasoning, that is L1.

### Level 2 — Specialist

- Operates autonomously on routine tasks. Names the pattern, gives a concrete example from experience.
- Example evidence: "I added a composite index on (user_id, created_at) when our dashboard queries became slow; it dropped latency from 800ms to 40ms."
- Mapping: concrete example + one correct trade-off mentioned = L2.

### Level 3 — Expert

- Systematic trade-off reasoning. Considers failure modes. Can justify choices in terms the candidate understands independently of the interviewer's prompt.
- Example evidence: "I'd avoid a partial index here because the predicate would shift over time — the index would be useless within a quarter. A BRIN index might be better for append-mostly data."
- Mapping: multiple trade-offs weighed + one correct failure mode identified = L3.

### Level 4 — Proficient

- System-level judgement. Can step back and question the framing of the problem. Discusses organisational / operational dimensions alongside the technical.
- Example evidence: "Before we add more indexes I'd want to understand the read/write ratio and whether the dashboard is the bottleneck at all. Sometimes the answer is to cache at a higher layer and leave the DB alone."
- Mapping: reframes the problem AND proposes a principled alternative = L4.

---

## Meta-rules

1. **Anchor to the descriptor, not the prestige.** A candidate using advanced vocabulary without concrete evidence is not higher-level; they may simply know the terms.
2. **Prefer lower when straddling.** If evidence supports L2 unambiguously and L3 partially, assign L2. Note the L3 partial in the rationale.
3. **Missing evidence ≠ lower level.** A turn that does not exercise higher-level reasoning is not evidence of lower-level capability. It is evidence of "not assessable from this turn".
4. **Width vs depth.** One good trade-off > five casual name-drops. Depth wins.
5. **Silent in one dimension.** If the candidate shows L3 reasoning about trade-offs but L1 knowledge of the specific mechanism, assess the mechanism node L1, and record a rationale that notes the dimension gap. Do not average.
6. **Negative signals.** A candidate who says "I don't know" is neither a red flag nor a level signal by itself. Record an empty assessment.

---

## Confidence calibration

- `0.9` — Evidence is direct and decisive; the descriptor match is near-exact.
- `0.7` — Evidence is clear but partial, or the descriptor is open to interpretation.
- `0.5` — Evidence is indirect; the candidate spoke around the topic but did not hit the descriptor.
- `0.3` — Evidence is weak; the level is an educated guess. **Triggers `needs_manual_review`.**
- `<= 0.2` — Do not emit the assessment. Return empty array instead.
- `1.0` — Never. Perfect confidence is a bug.

---

## Red flags vs level

Red flags are **orthogonal** to the level. A candidate may demonstrate L3 trade-off reasoning while also stating something factually wrong. Record both.

Red flag priorities:

- `FACTUALLY_WRONG` — incorrect verifiable claim.
- `FABRICATED_TECHNOLOGY` — naming a product, API, or feature that does not exist.
- `CONTRADICTION` — internal contradiction across turns.
- `LIKELY_CHEATING` — near-verbatim canonical source.
- `RED_FLAG_OTHER` — other concerns; the recruiter adjudicates.

Use `FABRICATED_TECHNOLOGY` sparingly — only when you are highly confident the thing does not exist. When in doubt, downgrade to `FACTUALLY_WRONG`.
