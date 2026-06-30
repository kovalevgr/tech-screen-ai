# 16 — Recruiter Position Templates

Manage Position Templates: a list of templates and a create/edit form.

**Routes:** `/positions` (list), `/positions/new` (create), `/positions/[id]` (edit).
**Audience:** recruiter / admin.
**Language:** Ukrainian labels; level names kept as the contract enum (Junior / Middle / Senior / Tech Leader); technical terms English where awkward.

---

## Baseline Check

- **Reference read:** `hellow_page.png`, `admin_page.png`.
- **Surfaces:** `surface.base` (white) page canvas; the list rendered in a `Card` (`radius.lg`) over the base; muted `surface.muted` table header row; the existing shell sidebar/top-bar unchanged.
- **Brand orange used in:** the single primary CTA per screen (`+ Нова позиція` on the list; `Зберегти` on the form), the `← Назад до позицій` back-link, the filled state of checkboxes (stacks / competencies / must-have), and the focus ring. Nothing else.
- **Typography:** `text.title` page heading; `text.small` uppercase for table column headers; `text.body-dense` (14 px) for table rows and form controls (recruiter density, §3); `text.body` for form field labels.
- **Radius:** `radius.md` on buttons / inputs / select; `radius.lg` on the card; `radius.sm` on checkboxes; `radius.xl` on the archive-confirm dialog; `radius.pill` on the status chip.
- **Divergences from baseline:** none.

---

## Purpose

Let a recruiter define and maintain the roles to interview for. A Position
Template names a role, sets its level, and selects the rubric stacks +
competencies (flagging the must-haves) that an interview will assess. The form's
options come from the **active rubric** so the recruiter never types ids.

---

## States

### List — loaded (default), `/positions`

- Section heading `Шаблони позицій` + a muted count (`N активних`).
- A `Card` wrapping a `Table`: columns **Назва · Рівень · Стеки · Компетенції · Статус · Дії**.
  - `Стеки` / `Компетенції` show counts.
  - `Статус` is a pill: `Активна` (neutral) / `Архівована` (muted).
  - `Дії` per row: `Редагувати` (link/ghost) and `Архівувати` (ghost; opens confirm). Archived rows show no `Архівувати`.
- A single primary CTA top-right of the heading row: `+ Нова позиція` → `/positions/new`.
- An `Показати архівовані` toggle (checkbox/switch) above the table; off by default → only active rows; on → includes archived (visibly marked).

### List — loading

- shadcn skeleton rows in the table body (layout is known), not a spinner.

### List — empty

- `EmptyState`: heading `Ще немає жодної позиції`, prose `Створіть перший шаблон позиції, щоб почати.`, and the `+ Нова позиція` CTA. Never "no data".

### List — error

- Inline error panel: `Не вдалося завантажити позиції.` + a `Спробувати ще раз` action.
- **Unavailable / auth states** (degrade, never a broken page):
  - 404 (feature off) → `Розділ позицій недоступний.`
  - 401 (not signed in) → `Потрібен вхід.` (sign-in is T07).
  - 403 (wrong role) → `Недостатньо прав.`

### Form — create / edit, `/positions/new` · `/positions/[id]`

- `← Назад до позицій` back-link (orange).
- Heading: `Нова позиція` / `Редагувати позицію`.
- Fields (label above control; gaps per spacing rules):
  - `Назва` — text input (required, 1–200).
  - `Рівень` — Select (Junior / Middle / Senior / Tech Leader).
  - `Опис вакансії` — Textarea (optional).
  - `Стеки` — checkbox group from the active rubric (stack names).
  - `Компетенції` — checkbox group **scoped to the chosen stacks**; each checked competency exposes an `Обовʼязкова` (must-have) checkbox.
- Footer button row (primary on the right, §13): `Скасувати` (ghost/secondary) · `Зберегти` (primary).
- **Validation**: client checks mirror the contract (level set, ≥1 competency, must-have ⊆ selected, competency belongs to a selected stack); server `422` is surfaced inline next to the offending field, input preserved.
- **Edit load**: GET the template → prefill; save sends the full desired sets (PATCH replaces wholesale).
- **Form loading / error**: skeleton while the rubric + template load; if the active rubric can't load, show `Не вдалося завантажити рубрику; створення недоступне.` and disable submit (no template can be built without options).

---

## Layout

Single column inside the shell content slot. List: heading row (title + count left, CTA right) → toggle → `Card`/`Table`. Form: back-link → heading → vertical field stack in a `Card` → button row. Body width capped (`max-w-prose` / `max-w-[64ch]`) for readable Ukrainian.

## Interactions

- **Create**: `+ Нова позиція` → form → `Зберегти` → on success return to `/positions` with the new row present (cache invalidated).
- **Edit**: row `Редагувати` → form prefilled → `Зберегти` → list reflects the change.
- **Archive**: row `Архівувати` → confirm `Dialog` (`radius.xl`): `Архівувати позицію?` / `Її буде приховано зі списку, але дані збережуться.` / `Архівувати` (primary) · `Скасувати`. Destructive-style confirm is a separate dialog, never inline (§13). On confirm → row leaves the default list.
- Selecting/deselecting a stack updates the competency group (competencies outside the selected stacks are removed).

## Accessibility (WCAG 2.2 AA)

- Every input has a programmatic `<Label>` (not placeholder-only).
- Checkbox groups use a `fieldset`/`legend` (stacks, competencies).
- Icon-only actions get `aria-label`.
- Focus ring visible (shadcn default kept); full keyboard reachability.
- Status pills convey state by text, not colour alone.
- Confirm dialog traps focus and is escapable.

## Components used

- `Table`, `Card`, `Button`, `Input`, `Label`, `Select` (new), `Textarea` (new), `Checkbox` (new), `Dialog`, `Badge`/pill, skeleton.
- Feature components: `PositionTable` (list + row actions + archive confirm), `PositionForm` (create/edit).

## Ukrainian copy (chrome strings)

| Key | Ukrainian |
| --- | --- |
| page title | Шаблони позицій |
| new CTA | + Нова позиція |
| columns | Назва · Рівень · Стеки · Компетенції · Статус · Дії |
| show archived | Показати архівовані |
| status active / archived | Активна / Архівована |
| row actions | Редагувати · Архівувати |
| empty | Ще немає жодної позиції — Створіть перший шаблон позиції, щоб почати. |
| form headings | Нова позиція · Редагувати позицію |
| field labels | Назва · Рівень · Опис вакансії · Стеки · Компетенції · Обовʼязкова |
| form buttons | Скасувати · Зберегти |
| back link | ← Назад до позицій |
| archive confirm | Архівувати позицію? — Її буде приховано зі списку, але дані збережуться. |
