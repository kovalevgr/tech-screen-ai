# Assessor — level prompting guide — v0003

Levels 1–5 are defined by the rubric node's explicit L1–L5 descriptors. Level 0 (None) is defined here — rubric files carry no descriptor for it. This guide tells you how to _interpret_ the descriptors consistently and when 0 applies.

---

## The six states

The proficiency scale has six states, 0–5. Levels 1–5 map onto the rubric node's level descriptors; treat those descriptors as the authoritative definition for that node. This guide adds only meta-rules for how to map evidence to the descriptors. Level 0 is assessor-only.

### Level 0 — None

- A positive finding of absence, not a missing data point. The interviewer probed the competency; the candidate attempted substantively and demonstrated no relevant proficiency.
- Example evidence: asked twice how they would find a slow query, the candidate answers "I would restart the server" and, after rephrasing, "I would add more RAM" — no mention of any relevant mechanism.
- Mapping: probe(s) present in the turn context + substantive attempt(s) with wrong fundamentals or no relevant content = L0. Quote the failed attempts in `evidence_spans`.
- NOT level 0: a single "Не знаю", a trivially short answer, or a turn where the competency was never probed. Those are "not assessable" — return an empty `assessments` array.

### Level 1 — Basic

- Recognition without depth. Can name the thing correctly; cannot yet operate it autonomously.
- Example evidence: "I know about database indexes — they make queries faster."
- Mapping: awareness and basic correct naming, but no trade-off reasoning and no concrete operating experience, that is L1.

### Level 2 — Competent

- Operates autonomously on routine tasks. Names the pattern, gives a concrete example from experience.
- Example evidence: "I added a composite index on (user_id, created_at) when our dashboard queries became slow; it dropped latency from 800ms to 40ms."
- Mapping: concrete example + one correct trade-off mentioned = L2.

### Level 3 — Advanced

- Systematic trade-off reasoning. Considers failure modes. Can justify choices in terms the candidate understands independently of the interviewer's prompt.
- Example evidence: "I'd avoid a partial index here because the predicate would shift over time — the index would be useless within a quarter. A BRIN index might be better for append-mostly data."
- Mapping: multiple trade-offs weighed + one correct failure mode identified = L3.

### Level 4 — Proficient

- System-level judgement. Can step back and question the framing of the problem. Discusses organisational / operational dimensions alongside the technical.
- Example evidence: "Before we add more indexes I'd want to understand the read/write ratio and whether the dashboard is the bottleneck at all. Sometimes the answer is to cache at a higher layer and leave the DB alone."
- Mapping: reframes the problem AND proposes a principled alternative = L4.

### Level 5 — Expert

- Authoritative, first-principles command of the domain, including its internals and edge behaviour. Corrects or sharpens the question's premise accurately, anticipates second-order effects across systems and over time, and can articulate where the standard advice breaks down.
- Example evidence: "The composite index helps until the planner's row estimates drift — with this skew, autovacuum's default analyze threshold will lag and you'll flip to a seq scan under load. I'd pin statistics targets on those two columns first, and honestly, at this write volume I'd question whether the dashboard belongs on the OLTP primary at all."
- Mapping: correct internals-level reasoning + accurate anticipation of a non-obvious failure the interviewer did not hint at + principled reframing = L5. Vocabulary alone never earns L5.

---

## Meta-rules

1. **Anchor to the descriptor, not the prestige.** A candidate using advanced vocabulary without concrete evidence is not higher-level; they may simply know the terms.
2. **Prefer lower when straddling.** If evidence supports L2 unambiguously and L3 partially, assign L2. Note the L3 partial in the rationale.
3. **Missing evidence ≠ lower level.** A turn that does not exercise higher-level reasoning is not evidence of lower-level capability. It is evidence of "not assessable from this turn". Level 0 is not the floor of this rule — it requires its own demonstrated-absence evidence (see Level 0 above).
4. **Width vs depth.** One good trade-off > five casual name-drops. Depth wins.
5. **Silent in one dimension.** If the candidate shows L3 reasoning about trade-offs but L1 knowledge of the specific mechanism, assess the mechanism node L1, and record a rationale that notes the dimension gap. Do not average.
6. **Negative signals.** A candidate who says "I don't know" once is neither a red flag nor a level signal by itself. Record an empty assessment. Only repeated substantive failure under probing earns L0.
7. **0 vs empty array.** Level 0 asserts "the competency is absent" and needs evidence of failed attempts. An empty `assessments` array asserts "this turn cannot tell". When unsure between the two, return the empty array.

---

## Confidence calibration

- `0.9` — Evidence is direct and decisive; the descriptor match is near-exact.
- `0.7` — Evidence is clear but partial, or the descriptor is open to interpretation.
- `0.5` — Evidence is indirect; the candidate spoke around the topic but did not hit the descriptor.
- `0.3` — Evidence is weak; the level is an educated guess. **Triggers `needs_manual_review`.**
- `<= 0.2` — Do not emit the assessment. Return empty array instead.
- `1.0` — Never. Perfect confidence is a bug.

These bands apply to level 0 exactly as to levels 1–5: a hesitant 0 (confidence 0.3) triggers manual review like any other hesitant level.

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

A level-0 assessment is not itself a red flag, and a red flag does not force level 0. A candidate can be L0 on one node with zero red flags (honest absence), or L3 with a `FACTUALLY_WRONG` flag (strong reasoning, one wrong claim).
