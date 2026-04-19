# Candidate-facing string: session opening

Rendered as the Interviewer's first turn at session start. This string is **fixed**, not generated — the LLM is not asked to produce it. Consistency of the opening matters for calibration (every session starts from the same baseline) and for candidate comfort.

---

## String (Ukrainian)

> Вітаю, {FirstName}! Мене звати Інтерв'юер — я допоможу провести сьогоднішнє технічне інтерв'ю.
>
> Процес буде таким: я ставитиму вам питання за напрямом {Area}, уважно слухатиму і, за потреби, проситиму уточнень. Сесія триватиме приблизно {ExpectedMinutes} хвилин. Ви можете відповідати у власному темпі — немає жорстких таймерів.
>
> Якщо ви не знаєте відповідь — так і скажіть, це нормально. Ми просто перейдемо далі.
>
> Почнемо?

---

## Variables

| Name | Source | Notes |
| --- | --- | --- |
| `{FirstName}` | `candidate.first_name` | Fallback: "колего" if null |
| `{Area}` | `interview_plan.area_label_uk` | Free-form Ukrainian area label, e.g., "Backend-розробка" |
| `{ExpectedMinutes}` | `interview_plan.expected_minutes` | Integer; fallback: "30" |

Variables are substituted by the orchestrator before sending the string as the session's first turn.

---

## Behaviour

- Sent as the first turn at session start, before any LLM call.
- The candidate's reply to this turn is the first "real" candidate turn; it is logged but not assessed (it is typically a one-word affirmation).
- If the candidate types a substantive answer instead of an affirmation, the orchestrator proceeds to the first planned seed question regardless — the opening is a pleasantry.

---

## Document versioning

- v1.0 — 2026-04-18.
