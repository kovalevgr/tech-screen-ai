# 14 — Recruiter Session Review

Post-session review with assessments, corrections, and audit trace.

**Route:** `/sessions/[id]/review`.
**Audience:** recruiter.
**Language:** Ukrainian chrome; English technical fields.

---

## Purpose

This is the primary workspace for the recruiter. They read the dialogue, see the Assessor's output, agree or disagree (submitting corrections that become new rows, not updates), and record a final session decision.

---

## States

### Assessed

- Dialogue on the left.
- Assessment panel on the right, anchored to the currently focused turn.
- Rubric tree below the assessment panel with coverage overlay.
- Sticky footer: session-level decision ("Рекомендовано", "Не рекомендовано", "Потрібна друга думка") and a free-text decision rationale.

### Needs manual review

- Badge on the session header: `NEEDS_MANUAL_REVIEW` (warning).
- Assessments that failed schema / low-confidence are flagged and the recruiter is asked to complete them manually before recording the decision.

### Corrections exist

- Any assessment with a correction shows a "+N corrections" indicator; clicking expands the correction history inline.

---

## Layout

Three zones:

1. **Header** — candidate name, `SessionStateChip`, position, date, action menu (export, archive, copy link).
2. **Main split** (lg+):
   - Left (3/5): `DialoguePane` with `TurnBubble`s; each bubble clickable to focus.
   - Right (2/5): tabs — "Оцінка" (default), "Rubric", "Trace".
3. **Footer** — session decision, rationale, submit button.

On md: single column, tabs move above the dialogue pane, footer stays sticky.

---

## Tabs

### "Оцінка" (Assessment)

- `AssessmentPanel` anchored to the focused turn.
- Shows level per competency, confidence, red flags, reasoning.
- "Внести корекцію" button opens `CorrectionModal`.

### "Rubric"

- `RubricTree` with coverage overlay. Competencies with coverage show level chips; empty branches are visually muted.
- Hovering a node shows the turns that contributed.

### "Trace"

- `TraceInspector` drawer with `turn_trace` entries for this turn: prompt hashes, truncated prompt body, raw output, parsed JSON, cost, latency.

---

## Interactions

- **Focus a turn** by clicking it in the dialogue. The assessment panel scrolls to that turn's assessment.
- **Submit a correction** — open `CorrectionModal`, fill new levels / flags / reason, save. A new `assessment_correction` row is written.
- **Record session decision** — footer form. Saving transitions the session to `DECIDED` and locks the dialogue pane.

---

## Accessibility

- All three tabs are keyboard-reachable.
- Correction modal traps focus while open.
- Level chips have an `aria-label` including the numeric level and its Ukrainian name ("Рівень 2 — Спеціаліст").

---

## Components used

- `DialoguePane`, `TurnBubble`
- `AssessmentPanel`, `CorrectionModal`
- `RubricTree`
- `TraceInspector`
- `Tabs`, `Button`, `Dialog`, `Badge`
