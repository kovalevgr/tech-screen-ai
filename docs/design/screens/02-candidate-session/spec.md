# 02 — Candidate Session

The live session screen. Candidate and AI interviewer exchange turns until the orchestrator ends the session.

**Route:** `/sessions/[token]`.
**Audience:** candidate.
**Language:** Ukrainian.

---

## Purpose

Host the dialogue calmly and transparently. The candidate sees what the interviewer said, what they answered, and what is happening next. Nothing else.

The candidate does not see: assessments, scores, rubric, red flags, coverage, cost, or the plan. These are reviewer-facing.

---

## States

### Active

- Header with candidate name and session progress (abstract: "question X of approximately Y", no count-down timer).
- Dialogue pane fills the centre.
- Input area at the bottom.

### Waiting for interviewer

- The last candidate turn is rendered.
- A quiet "typing" indicator (three dots) appears below, inside a ghost bubble, not as a spinner.

### Paused (`SESSION_PAUSED_UPSTREAM`)

- `PauseOverlay` fades in over the dialogue.
- Dialogue is dimmed, not hidden. Candidate can see prior context.
- Input is disabled.

### Halted (`SESSION_HALTED_*`)

- Full-screen calm message with `status.warning` accent (not `danger`).
- Copy explains the recruiter will be in touch; candidate's work is saved.

### Completed

- Auto-navigate to `03-candidate-completed` after the final turn is rendered and acknowledged by the candidate (a "Дякую, завершити" button on the last interviewer turn).

---

## Layout

Three zones stacked:

1. **Header** — `SessionHeader` variant for candidates: logo, candidate name (right-aligned), small "Пауза" button. Height `space.16`.
2. **Dialogue pane** — `DialoguePane` with `TurnBubble`s. Scrolls; auto-scrolls to new turns unless the candidate has scrolled up. `max-w-[720px]` centred.
3. **Input area** — sticky bottom, `max-w-[720px]` centred. One multiline input (auto-resize up to 8 lines), a send button, a character counter that only appears near the 8000-char soft cap.

The pause button opens a modal: "Зробити коротку паузу?" — options "Так" / "Ні". On "Так" the session transitions to `SESSION_PAUSED_CANDIDATE` and the overlay appears with a "Продовжити" button.

---

## Interactions

- **Send** is `Ctrl / Cmd + Enter` or click. `Enter` alone creates a newline.
- **Typing** is local; the candidate's turn is only transmitted on send.
- **Receiving** streams the interviewer response character-by-character (30–60 cps target; slow enough to read, fast enough to not feel artificial).
- **Scroll** behaviour: auto-scroll on new turns unless the user is scrolled up > 80 px from the bottom; then a "↓ Нові повідомлення" pill appears.

---

## Accessibility

- Dialogue pane is an `aria-live=polite` region so screen readers announce new interviewer turns.
- Input has a visible label "Ваша відповідь" (above, not placeholder).
- Pause button is reachable via keyboard; `Escape` inside the pause modal closes it.
- Reduced motion disables the streaming animation — the full response appears at once.

---

## Components used

- `SessionHeader` (candidate variant)
- `DialoguePane`
- `TurnBubble`
- `PauseOverlay`
- `Button`
- `Dialog` (pause confirmation, halted overlay)

---

## Copy hooks

Candidate-facing strings (opening, pause, halted, closing) live in `prompts/shared/candidate-facing/` and are referenced by id. UI chrome strings (header labels, button labels) live in the frontend i18n file.

---

## Not in scope for MVP

- Voice input / voice output.
- File attachments in answers.
- Code blocks with syntax highlighting.
- Drawing board for whiteboard-style questions.

All four are deferred; see `project_techscreen_deferred.md`.
