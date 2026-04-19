# Candidate-facing string: pause

Shown as the `PauseOverlay` body when the session is in `SESSION_PAUSED_UPSTREAM` (a Vertex outage or similar transient upstream issue).

---

## String (Ukrainian)

> **Коротка пауза**
>
> Ми тимчасово призупинили сесію — це з нашого боку, не з вашого. Ваші відповіді збережено в повному обсязі.
>
> Продовжимо автоматично, щойно все буде готово. Будь ласка, зачекайте — зазвичай це займає до хвилини.

---

## Halted variant (`SESSION_HALTED_UPSTREAM`)

Used if the pause exceeds the threshold (3 minutes by default) and the orchestrator halts the session for rescheduling.

> **Сесію призупинено до перепланування**
>
> Виникла тривала технічна пауза, і ми не хочемо продовжувати в такому форматі. Ваші відповіді збережено, рекрутер зв'яжеться з вами найближчим часом для перепланування.
>
> Дякуємо за розуміння.

---

## Candidate-initiated pause variant

Used when the candidate clicks the "Пауза" button.

> **Пауза**
>
> Не поспішайте. Сесія збережена; ви можете продовжити, натиснувши "Продовжити".

---

## Behaviour

- Displayed by the frontend based on the current `SessionState`.
- Text is identical across sessions; no variables except the optional elapsed time line in debug mode.
- No error-coloured styling (`status.warning`, not `status.danger`). See `docs/design/principles.md` §2.

---

## Document versioning

- v1.0 — 2026-04-18.
