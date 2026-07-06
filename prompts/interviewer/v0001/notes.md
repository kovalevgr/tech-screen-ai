# Interviewer — v0001 — notes

## What changed

Initial version. First Interviewer prompt for MVP.

## Why

Establish a baseline for calibration and a reference point for future prompt edits. Everything downstream (level guide, Ukrainian anchors) is pinned to this version.

## Design choices worth noting

- **Narrow output.** A single Ukrainian utterance plus an executed-move field. Deliberately minimal — we rely on the orchestrator for everything that isn't "the next thing the candidate reads".
- **No rubric in the prompt.** The Interviewer does not see the rubric. This is a deliberate split: the Assessor uses the rubric; the Interviewer does not need it to conduct the dialogue.
- **Deterministic move selection.** `next_planned_move` is chosen by the Python state machine. The Interviewer executes, it does not decide. This is constitution §2 materialised at the prompt level.
- **Guardrails before forbidden.** "What to do when X" before "what never to do". Positive framing reads clearer.
- **Under-80-word utterance cap.** Longer interviewer turns dilute the question; 80 Ukrainian words is ~60 English words.

## Hypothesised behaviour

- Off-topic redirection triggers at three consecutive off-topic candidate turns. We expect roughly 1 in 15 sessions to hit this at least once.
- Distress reassurance triggers rarely (< 1 in 30) but is important when it does.
- Russian-language replies: silent Ukrainian response, no comment. Expected on some fraction of sessions.

## Known risks

- The model may occasionally produce meta-commentary ("As an AI interviewer..."). Forbidden item #9 is the hedge; calibration will tell us if it leaks.
- Level calibration may initially skew expert-heavy (Gemini tends toward longer, more formal Ukrainian than the target register). First calibration run will tell us.

## Calibration delta

N/A — initial version.

## Author

Ihor — 2026-04-18.

## Addendum — 2026-07-06

`schema.json` added to this version directory to codify the §4 output
contract of `system.md` as a machine-readable file — the T17 deliverable
named as T18's contract in `docs/engineering/implementation-plan.md` but
never created (assessor and planner already had one). No behavioural
change to the prompt text, hence no new prompt version. One caveat: the
1..1200-character `utterance` bounds are derived from guardrail §7
(~80 Ukrainian words), not stated in §4 itself — i.e. they are new
normative content introduced by `schema.json`, chosen conservatively as
a hard backstop above the prompt-level word cap.
