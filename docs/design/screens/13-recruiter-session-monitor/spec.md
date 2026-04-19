# 13 — Recruiter Session Monitor

Read-only live view of a session in progress.

**Route:** `/sessions/[id]/monitor`.
**Audience:** recruiter.
**Language:** Ukrainian UI chrome; dialogue renders in its original language (Ukrainian).

---

## Purpose

Let a recruiter watch a live session without intervening. Used sparingly — most reviews happen post-session. The monitor view exists for training, QA, and dealing with escalations.

---

## States

### Watching

- Dialogue pane streams turns as they complete.
- Side rail shows: current competency, state chip, token + cost ticker, time elapsed.
- No input — the recruiter cannot type on the candidate's behalf.

### Paused / halted

- Overlay banner over the dialogue ("Сесія на паузі", `status.warning`).
- Side rail continues to show state.

### Completed

- Banner "Сесія завершена" → CTA "Перейти до огляду" navigates to `14`.

---

## Layout

Same two-column shape as `14`, but the right rail is state/metrics, not assessments.

- Left: dialogue pane (read-only). Auto-scrolls on new turns.
- Right rail: live session state, current competency, turn count, elapsed time, LLM cost (approximate), "Перейти до плану" link.

---

## Interactions

- **Read-only.** No pause / halt controls. The candidate controls their own pause.
- **Escalation button** — non-blocking note the recruiter can attach to the session while watching; saved to `session_decision` with `type=watch_note`.

---

## Accessibility

- Dialogue pane is an `aria-live=polite` region.
- Cost ticker is polite too (announced on change, not on every character).

---

## Components used

- `DialoguePane`, `TurnBubble`
- `SessionStateChip`
- Cost / progress widgets (small, non-custom)
- `Textarea` for the escalation note
