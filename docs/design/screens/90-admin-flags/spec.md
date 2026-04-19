# 90 — Admin: Feature Flags

Toggles for feature flags whose state lives in the app DB (ADR-011).

**Route:** `/admin/flags`.
**Audience:** admin role only.
**Language:** English labels (internal / engineering-facing).

---

## Purpose

Let an admin flip flags without a migration. All flips are audited.

---

## States

### Default

- Table of flags: name, description, default from YAML, current override, audiences, last changed.
- Each row has a `Switch` for the "enabled" override and a `Select` for audience targeting.

### Save in progress

- Row shows a small spinner next to the switch.
- Toast on success.
- Toast on failure ("not saved; try again"), switch returns to previous state.

---

## Layout

Table-first, single column. Filter: search by flag name.

---

## Interactions

- **Toggle** — writes to the feature-flag override table, creating an `audit_log` row with the operator email.
- **Audience** — free-form tag list: `internal`, `pilot`, `n-ix-only`, `percentage:10`. Full audience spec lives in `configs/feature-flags.yaml`; the UI only surfaces the tags that YAML declares.

---

## Guardrails

- A flag defined in YAML with `immutable: true` cannot be flipped via UI.
- Flips are rate-limited to prevent a thundering accidental-toggle situation (max 10 flips per minute per operator).

---

## Accessibility

- Switches have `aria-label` "{flag name} — {on|off}".
- Changes are announced to screen readers.

---

## Components used

- `Table`, `Switch`, `Badge`, `Input`, `Toast`, `Tooltip`
- `FlagBadge` on rows whose flag is audience-scoped
