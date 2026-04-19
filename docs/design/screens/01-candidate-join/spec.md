# 01 — Candidate Join

The first screen a candidate sees after clicking the magic link delivered by email.

**Route:** `/sessions/[token]/join` (public, token-gated).
**Audience:** candidate.
**Language:** Ukrainian only.

---

## Purpose

Confirm the candidate is the intended recipient of the link, obtain consent for the recording and assessment process, and hand them off to the active session.

---

## States

### Happy path

1. Candidate lands on the page. The link validates in the background.
2. Page shows: greeting with the candidate's first name, a short explanation of what the session is (length, topic, that it is conducted by an AI interviewer), and a consent block.
3. Candidate reads consent, ticks the consent checkbox, clicks "Розпочати".
4. Browser navigates to `02-candidate-session`.

### Link expired / invalid

- Calm Ukrainian message: link is no longer valid, please contact the recruiter.
- No retry button. No technical details.

### Already-started session

- If the session is already in progress (candidate reloaded mid-session), redirect to `02` with the session state restored.
- If the session is `COMPLETED` or `CANCELLED`, show a message explaining that and a pointer to `03` if `COMPLETED`.

### Network / backend unavailable

- Spinner for up to 5 seconds. If still no response: a calm "we are experiencing a brief issue" message and a manual retry link. No error modal.

---

## Layout

Single column, centred, `max-w-[560px]`.

- Top: N-iX logo (small, `space.8` margin-top).
- Hero title: "Привіт, {FirstName}! Готові до інтерв'ю?" (`text.display`, `font.semibold`).
- Body: two or three short paragraphs in `text.body`, describing what happens next. Length, AI interviewer, that notes are taken, that a reviewer will look at the results afterwards.
- Consent block: `Card` with `text.body-dense` summarising consent points, `checkbox` + label "Я погоджуюся...".
- Primary CTA button "Розпочати" — enabled only when consent checkbox is ticked. Disabled state uses `content.muted`.
- Secondary link "Зв'язатися з рекрутером" opens a `mailto:` to the recruiter's email (passed with the token).

---

## Interactions

- The consent checkbox state is local; nothing is persisted until the candidate clicks "Розпочати".
- Clicking "Розпочати" calls `POST /api/sessions/{token}/start`, then navigates.
- No auto-start. No timer. The candidate begins when they are ready.

---

## Accessibility

- Logical reading order: logo → title → body → consent → CTA.
- Checkbox has a programmatic label; the entire consent text is not inside the label (legible, but screen readers read the summary link separately).
- CTA focus state uses `focus.ring`.
- Page is usable with keyboard only.

---

## Components used

- `Card` (shadcn)
- `Checkbox` (shadcn)
- `Button` (shadcn)
- `SessionHeader` — minimal variant (logo only)
- `EmptyState` — reused for invalid link message

---

## Copy draft (Ukrainian)

> **Привіт, {FirstName}! Готові до інтерв'ю?**
>
> Це технічне інтерв'ю за напрямом {Area}. Триватиме приблизно 30 хвилин. Вас супроводжуватиме AI-інтервʼюер: він задаватиме питання, уважно слухатиме і згодом підготує резюме для рекрутера-людини.
>
> Ваші відповіді не оцінюються в реальному часі — тільки після завершення, уже рекрутером, з можливістю корекцій. Це частина нашого дбайливого процесу.
>
> [ ] Я погоджуюся з умовами участі та обробкою даних для цілей рекрутингу.
>
> [Розпочати] [Зв'язатися з рекрутером]

Final copy is reviewed by the N-iX recruiting lead before MVP launch.

---

## Not in scope for MVP

- Video / audio permission prompt (session is text-only at MVP).
- Browser check modal.
- Bandwidth check.
