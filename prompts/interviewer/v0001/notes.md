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
