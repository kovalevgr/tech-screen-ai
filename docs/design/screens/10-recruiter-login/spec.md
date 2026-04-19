# 10 — Recruiter Login

Google Workspace SSO entry point for internal users.

**Route:** `/login`.
**Audience:** recruiter / admin / engineer.
**Language:** Ukrainian + English (labels Ukrainian, error messages bilingual).

---

## Purpose

Authenticate an internal user via Google Workspace and deliver them to the dashboard.

---

## States

### Default

- N-iX logo.
- "Увійти через Google Workspace" button.
- Short footer explaining this is an N-iX-internal tool.

### Already authenticated

- Redirect straight to `/dashboard` without rendering.

### Auth failed / not authorised

- Message: "Обліковий запис не має доступу до TechScreen. Зверніться до адміністратора."
- Link to contact admin (mailto).

---

## Layout

Single centred column, `max-w-[420px]` on a `surface.base` canvas. The N-iX wordmark sits at the top of the column in `brand.primary`, with the "Увійти через Google Workspace" button immediately below it (primary fill, `radius.md`). Light theme only — no theme toggle (principle §6).

---

## Accessibility

- Single primary action; large, keyboard-focusable.
- Error states use text + icon, never colour alone.

---

## Components used

- `Button` (shadcn, with Google icon)
- Simple prose

---

## Not in scope

- Email / password fallback. Workspace SSO only.
- Multi-tenancy. Single N-iX Workspace is the only identity provider.
