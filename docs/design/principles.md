# Design Principles

How TechScreen looks, reads, and feels. These principles exist so design decisions across screens stay consistent without re-litigating the same questions.

The stack is fixed: Next.js + Tailwind + shadcn/ui + lucide-react. These principles tell us how to use that stack, not whether to use it.

---

## 1. Ukrainian-first, English-ready

The candidate-facing UI is Ukrainian. Strings in the interviewer dialogue, candidate instructions, and the consent copy are authored in Ukrainian, never machine-translated at runtime.

Recruiter-facing UI is bilingual: primary labels Ukrainian, technical terms kept in English where a Ukrainian form would be awkward (e.g., "rubric", "snapshot", "commit").

**What this means for components.** Long strings exist. Typography and layout must gracefully accept 30–40 % longer Ukrainian text compared to the English source. No fixed-width labels. No `text-ellipsis` on primary interactive copy.

---

## 2. Calm under pressure

Candidates use the product during a high-stakes moment. The UI must not add stress.

- No modal pop-ups during an active session.
- No flashing, no "error!" toasts in red when the system can silently retry.
- Pauses and errors are framed in a reassuring tone ("We are experiencing a brief pause. Please wait.").
- No progress bars that imply the candidate is being timed on a specific question.
- No leaderboards, no scores visible to the candidate.

Recruiters can handle denser, more information-rich interfaces. Candidates get one thing at a time.

---

## 3. Information density matches the role

- **Candidate screens:** one task per screen. Generous whitespace. Text at 16 px body minimum.
- **Recruiter session-review screens:** tabular, dense, keyboard-navigable. 14 px body acceptable.
- **Dashboards:** dense but never sacrificing readability for count. Prefer 20 rows per page with good typography over 50 rows in 11 px.

---

## 4. Auditability over prettiness

Every piece of data the recruiter sees should be inspectable back to its source:

- Every assessment shows the turn trace it came from.
- Every correction shows who made it and when.
- Every feature-flag gated element is visibly labelled in the recruiter UI ("beta" badge, for instance).

We prefer a slightly less elegant layout with a visible audit link over a clean layout that hides provenance.

---

## 5. Accessibility is a floor

- **WCAG 2.2 AA** is the minimum for all screens. No 2.5 AAA yet; AA is enforced in CI via `axe-core` runs in Playwright tests.
- **Colour contrast:** 4.5:1 for body text, 3:1 for large text. Interactive states (hover, focus) remain compliant.
- **Keyboard navigation:** every interactive element reachable via Tab; focus ring visible (shadcn's default is acceptable; do not remove it).
- **Screen reader:** every icon button has an `aria-label`. Form inputs have programmatic labels, not placeholder-only.
- **Reduced motion:** respect `prefers-reduced-motion`. No auto-playing animations.

Accessibility bugs block merge. The reviewer sub-agent flags them.

---

## 6. Light-first, single accent

The product is a light-theme product. White canvas, one subtle grey surface for secondary regions, strong but controlled brand accent (N-iX orange) for primary actions and identity marks only. This matches the N-iX reference designs in `docs/design/references/`.

- The candidate session and all recruiter screens ship light only at MVP.
- No theme toggle in the UI. No `dark:` Tailwind variants in the first cut.
- A future dark mode is a deliberate project, not a flag. When we do it, it ships alongside updated token tables and updated screenshots; it is not a free side-effect of `dark:` classes sprinkled through components.
- The brand accent is used sparingly: primary CTA, the active logo mark, the filled-checkbox state, a select emphasis word in headings. Everything else is neutral greys and black on white.

---

## 7. shadcn/ui first, custom second

When a shadcn primitive exists for a use case, use it. Customise via Tailwind and props. Do not fork the primitive and vendor it elsewhere.

Exceptions — write a custom component only when:

- No shadcn primitive maps to the concept (e.g., the turn-bubble, the rubric tree visualiser).
- The primitive cannot be styled via Tailwind to match the spec.

New custom components live in `app/frontend/src/components/<feature>/`. They go through design review before their first use in a screen.

---

## 8. Tokens, never hex

Colour, spacing, typography, radii come from tokens defined in `docs/design/tokens/` and exported as Tailwind theme extensions. Components reference tokens, not raw values.

Wrong:

```tsx
<div className="bg-[#1e293b] text-[15px] p-[18px]">
```

Right:

```tsx
<div className="bg-surface-muted text-body p-4">
```

A one-off deviation is a token bug. Fix the token, not the component.

---

## 9. Brand alignment with N-iX

TechScreen is internal to N-iX and wears the N-iX brand clearly but not loudly. The visual reference is `docs/design/references/` — an earlier N-iX internal tool (Chat-iX) with two screens we treat as the baseline:

- `hellow_page.png` — the welcome / workspace frame. Notice: white canvas, a muted grey sidebar, thin divider lines, the "N-iX" wordmark in brand orange in the top bar, a prominent `+ New …` primary CTA in the sidebar, generous vertical whitespace, large display text in brand orange as the empty-state hero.
- `admin_page.png` — a dense table page. Notice: the same chrome, the same orange used only for filled checkbox states and for the "Back to Chat" link-style back-button; everything else is neutral; the avatar is a grey circle with mono initial; action buttons are outline-style with small radius.

These screens set the tone. When designing a new TechScreen screen, open these references first and answer the question "would this feel like it belongs next to them?". If not, either the screen is wrong or the principle is wrong — raise it, do not drift.

The reference screens are **not pixel specs**. We do not reimplement them. We extract: palette, type scale, surface structure, density, radius, divider weight. Everything else is a decision for the screen spec.

---

## 10. Load state and empty state are first-class

Every screen spec includes at least:

- Loaded (happy path).
- Loading.
- Empty.
- Error.

Loading states use shadcn skeletons, not spinners, when the layout is known. Spinners only for truly unknown durations. Empty states are prose + next action, never "no data".

---

## 11. Motion

Motion communicates causation, not decoration.

- Transition between states: 150 – 200 ms, `ease-in-out`.
- Entering content: fade + 4 px translate, 200 ms.
- No parallax. No scroll-triggered showreels. This is a tool, not a landing page.
- `prefers-reduced-motion` disables all but opacity transitions.

---

## 12. Copy in the design

We write the real copy in the spec, not Lorem ipsum. Real copy surfaces the truncation risk, the tone mismatch, the localisation issue — placeholders hide all three.

Candidate-facing copy is drafted in Ukrainian and placed in `prompts/shared/candidate-facing/` when it is displayed by the interviewer; in the screen spec when it is plain UI chrome.

---

## 13. Consistency beats local optimum

If we already decided something for one screen, the next screen inherits it by default. A different choice needs a reason that is written down.

Examples that must stay consistent across the product:

- Primary action always on the right of a button row.
- Destructive action is a separate confirmation dialog, never inline.
- The candidate's name is shown the same way everywhere (full name, no diminutives).
- Time formats are Ukrainian locale (`dd.MM.yyyy HH:mm`).

---

## 14. What we are not designing

- A marketing site.
- A public product with sign-ups.
- A mobile app. (The candidate web UI must work on a laptop; tablet is best-effort; phone is out of scope at MVP.)
- A multi-tenant SaaS dashboard.

This keeps scope tight and keeps the component inventory small.

---

## Document versioning

- v1.1 — 2026-04-19. Light-first + N-iX brand orange adopted after referencing Chat-iX screens. §6 rewritten from "dark mode default recruiter" to "light-first, single accent". §9 tightened to point at the reference folder.
- v1.0 — 2026-04-18. Initial principles.
