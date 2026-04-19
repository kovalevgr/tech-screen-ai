# Design

This folder is the single source of truth for TechScreen's visual and interaction design.

## Structure

- `principles.md` — high-level design principles, brand alignment rules, accessibility baseline.
- `tokens/` — design tokens (colors, typography, spacing) derived from the company brand references.
- `components/` — component-level specs (button, message bubble, rubric card, etc.). Aligned with shadcn/ui primitives.
- `screens/` — per-screen specs. One folder per MVP screen with references, annotations, and a prose spec.
- `references/` — unsorted dump of reference screenshots. Everything lands here first, then we categorise into `screens/NN-xxx/` during grooming.

## Stack

- **Framework:** Next.js (App Router).
- **Component library:** shadcn/ui (copy-paste primitives on top of Radix).
- **Styling:** Tailwind CSS.
- **Icons:** lucide-react.

## Process

1. Drop reference screenshots into `references/` with descriptive filenames (`session-page-competitor-X.png`, `dashboard-existing-tool.png`).
2. During grooming, categorise each reference into the relevant `screens/NN-xxx/` folder or into `tokens/` if it illustrates a brand rule.
3. Per-screen `spec.md` is written as a prose description of the screen, its states, interactions, and the components it uses. Claude Code reads both the screenshots (multimodal) and the prose — prose is the fallback if the image is ambiguous or lost.

## How this hooks into Spec Kit

Any feature whose `plan.md` affects the frontend must have a **Design reference** section linking to `docs/design/screens/NN-xxx/spec.md` (and tokens if new ones are needed).
