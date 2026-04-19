# 03 — Candidate Completed

The screen shown after the session completes normally.

**Route:** `/sessions/[token]/completed`.
**Audience:** candidate.
**Language:** Ukrainian.

---

## Purpose

Acknowledge the candidate's time, explain next steps, and close the tab calmly. No scores, no ranking, no "how did you do".

---

## States

### Completed normally

- Thank-you heading.
- Two short paragraphs: we received your answers; a recruiter will review them within N business days; they will contact you regardless of outcome.
- Contact link (mailto).
- No CTA to "see results" — there are none to see from the candidate's side.

### Halted mid-session (redirect here from `02`)

- Same layout, different copy: the session did not complete as expected; we have saved your work; the recruiter will be in touch.

---

## Layout

Single column, centred, `max-w-[560px]`, mirrors `01`.

- N-iX logo at top.
- Hero heading (`text.display`).
- Body prose (`text.body`), two paragraphs.
- Contact link.
- No primary CTA. The candidate closes the tab when ready.

---

## Accessibility

- Reading order flows top to bottom.
- Mailto link has a visible label; the email address is not relied on as the only visual signal.

---

## Components used

- `SessionHeader` (minimal)
- Prose block (no custom component required)

---

## Copy draft

> **Дякуємо за участь!**
>
> Ми отримали ваші відповіді. Рекрутер ознайомиться з матеріалами інтерв'ю упродовж кількох робочих днів і повернеться з відповіддю незалежно від результату.
>
> Якщо виникнуть питання — напишіть нам: [recruiter-email].
