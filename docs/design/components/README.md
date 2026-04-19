# Components

Inventory of UI components TechScreen uses. Two kinds:

1. **shadcn/ui primitives** — imported from `@/components/ui/*`, installed via the shadcn CLI. We do not fork them; we style them via Tailwind props.
2. **Custom components** — TechScreen-specific concepts with no shadcn equivalent. They live in `app/frontend/src/components/<feature>/`.

Adding a custom component is a design-review moment: write a short spec under `components/<component>.md` describing purpose, states, props, and the screens that use it.

**Visual baseline:** open `docs/design/references/hellow_page.png` and `docs/design/references/admin_page.png` before designing or reviewing a component. The chrome (top bar with centred title, a subtle-grey sidebar, thin 1-px dividers, brand-orange primary CTA, avatar circles, outline secondary buttons with small radius, filled orange checkboxes) is the shared shell all TechScreen components live inside.

---

## shadcn primitives in use

We install primitives on-demand via `pnpm dlx shadcn-ui@latest add <primitive>`. Current inventory:

| Primitive | Use |
| --- | --- |
| `button` | All CTAs and secondary actions |
| `input` | Text inputs |
| `textarea` | Free-text answers (rare; candidate answers are typed into the session box, not `textarea`) |
| `label` | Paired with every input |
| `form` | React Hook Form + Zod resolver, recruiter admin screens |
| `select` | Dropdowns in recruiter forms |
| `checkbox` | Filters, toggles |
| `switch` | Feature flag toggles in admin |
| `card` | Panels and grouping |
| `dialog` | Destructive confirmations, corrections modal |
| `sheet` | Slide-over for session detail inspector |
| `dropdown-menu` | Row actions in tables |
| `popover` | Annotations, rubric node previews |
| `tooltip` | Icon-only button labels, truncated text |
| `tabs` | Session review tabs (Dialogue / Assessment / Trace) |
| `table` | Dashboard list, audit tables |
| `badge` | Status pills, level chips, red flags |
| `avatar` | Candidate / recruiter avatars |
| `separator` | Row dividers |
| `skeleton` | Loading states |
| `toast` | Non-blocking notifications (save complete, correction submitted) |
| `alert` | Inline warnings (calibration warning, upstream paused) |
| `scroll-area` | Dialogue pane, long lists |
| `command` | Quick search across sessions (recruiter) |

Primitives not in this list are not used. Adding a primitive to the product is a PR that updates this table.

---

## Custom components

Each listed below has (or will have) a dedicated `.md` spec in this folder. The inventory is the contract.

### `TurnBubble`
Renders a single interviewer or candidate turn. Props: `sender`, `authoredAt`, `body`, `state` (sent / receiving / error). See [`turn-bubble.md`](./turn-bubble.md).

### `DialoguePane`
The scrolling container for `TurnBubble`s in candidate and recruiter views. Handles auto-scroll on new turn and scroll-position restore. See [`dialogue-pane.md`](./dialogue-pane.md).

### `RubricTree`
Recursive view of the `rubric_snapshot` with per-node coverage and assessment overlay. Expand / collapse, keyboard-navigable. See [`rubric-tree.md`](./rubric-tree.md).

### `AssessmentPanel`
Recruiter-facing panel that shows Assessor output for the current turn or the whole session: levels, red flags, confidence, raw JSON. Supports correction flow. See [`assessment-panel.md`](./assessment-panel.md).

### `CorrectionModal`
Form for submitting an `assessment_correction`. Fields: new level(s), red flag changes, reason. Append-only; never overwrites the prior assessment. See [`correction-modal.md`](./correction-modal.md).

### `SessionStateChip`
A status pill keyed to `SessionState`. Role mapping lives in `tokens/colors.md`. See [`session-state-chip.md`](./session-state-chip.md).

### `LevelChip`
Level 1–4 chip with colour and label. See [`level-chip.md`](./level-chip.md).

### `RedFlagBadge`
Small badge marking red flags (`FACTUALLY_WRONG`, generic). Clickable to show the trace that raised it. See [`red-flag-badge.md`](./red-flag-badge.md).

### `TraceInspector`
Drawer that shows `turn_trace` contents for a single LLM call: prompts (hash + truncated body), raw output, parsed JSON, token counts, cost, latency. See [`trace-inspector.md`](./trace-inspector.md).

### `SessionHeader`
Top bar on the candidate side (session progress abstract, pause button) and on the recruiter side (candidate name, session id, state chip, action menu). Two variants share the name. See [`session-header.md`](./session-header.md).

### `PauseOverlay`
Candidate-facing overlay shown during `SESSION_PAUSED_UPSTREAM`. Calm Ukrainian copy, no countdown timer, no error styling. See [`pause-overlay.md`](./pause-overlay.md).

### `EmptyState`
Shared empty-state layout (icon + heading + prose + CTA). Used on dashboards, search with no results, session lists. See [`empty-state.md`](./empty-state.md).

### `ConfirmDialog`
Wrapper over shadcn's `dialog` for destructive confirmations. Always requires an explicit "I understand" checkbox for truly destructive actions (deleting a rubric version, for instance). See [`confirm-dialog.md`](./confirm-dialog.md).

### `FlagBadge`
Tiny beta / experimental badge rendered next to feature-flag-gated UI in recruiter views (honesty over seamlessness). See [`flag-badge.md`](./flag-badge.md).

---

## Not-yet-built (deferred)

These are known future needs but are deferred past MVP. They will get specs when the need is real.

- `RubricEditor` — GUI editor for the rubric YAML. MVP edits via Git + PR only.
- `CalibrationDashboard` — interactive drill-down into calibration runs. MVP reports go to PR comments.
- `SessionTimeline` — visual timeline of session state transitions. MVP uses a plain list.

---

## Conventions for custom component specs

Each `components/<component>.md` contains:

1. **Purpose** — one paragraph, what it exists for.
2. **Props** — a typed list (name, type, required, default, description).
3. **States** — what the component can show (default, loading, empty, error, disabled, focused).
4. **Accessibility** — roles, labels, keyboard behaviour.
5. **Anatomy** — named subparts (header, body, footer) that a diagram or screenshot would point at.
6. **Variants** — if any.
7. **Used by** — a list of screen specs that render this component.

If the component is trivial (say, `FlagBadge`), the spec is short; that is fine. The structure keeps us honest.

---

## Document versioning

- v1.0 — 2026-04-18.
- Update this file when a primitive is added, a custom component is introduced, or a deferred component is promoted to in-use.
