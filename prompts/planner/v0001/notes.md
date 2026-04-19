# Planner — v0001 — notes

## What changed

Initial version.

## Why

First cut of the Pre-Interview Planner for ADR-006 Variant C (hybrid plan). Runs once per session before the candidate joins. Produces a plan the Interviewer executes verbatim and the orchestrator uses for deterministic routing.

## Design choices worth noting

- **Bounded output shape.** Each competency has at most three seed questions; each seed has at most two depth probes. Total plan size stays readable for the recruiter's plan-review screen (`12-recruiter-plan-review`).
- **Seed questions in Ukrainian; keyword triggers in English.** The candidate sees Ukrainian; the orchestrator matches English keywords in the candidate's answer to decide whether to fire a depth probe. This avoids brittle Ukrainian-string matching in orchestrator code.
- **`target_level + 1` ceiling.** A seed question at the target level (or one easier) gives us room to discover higher capability. Going two levels above risks the candidate writing off as "too hard" and affects morale + calibration.
- **Optional depth probes.** Omitting a probe is fine. Padded probes degrade the plan; empty arrays are honest.
- **Uses Gemini Pro (not Flash).** Per ADR-003 — planning is the only Pro-use case at MVP. The plan generation is heavier and higher-quality, and it runs once per session.

## Hypothesised behaviour

- Initial plans will be ~15–20% longer than budget on average (model tends to expand). Recruiters can trim in the plan-review screen.
- Seed question quality varies by competency maturity. Competencies with dense level descriptors produce better questions than sparse ones — this will drive rubric improvements.
- Depth probe triggers may be too broad ("mentions: ['database']") — expect calibration to tighten keyword specificity.

## Known risks

- **Plan drift from rubric.** The model may generate a question that does not actually probe the target level. Calibration catches this by measuring the level distribution of generated questions vs target.
- **Over-reliance on candidate profile.** If the recruiter provides "has experience with Kafka", the model may over-index on Kafka across competencies. The prompt forbids inventing profile detail, but not over-use of real detail.
- **Ukrainian drift toward formal.** Gemini Pro has a formal Ukrainian bias. Anchors help; calibration quantifies.

## Calibration delta

N/A — initial version.

## Author

Ihor — 2026-04-18.
