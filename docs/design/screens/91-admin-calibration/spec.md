# 91 — Admin: Calibration Report

Summary of the latest calibration run.

**Route:** `/admin/calibration`.
**Audience:** admin, engineer.
**Language:** English (internal / engineering-facing).

---

## Purpose

Show the latest calibration-run output at a glance. Detailed reports remain in PR comments and artefact storage; this screen is a convenient summary for "how are we doing right now".

---

## States

### Latest run available

- Run metadata: prompt version, model, dataset size, ran at, ran by.
- Summary metrics: exact-match %, within-0.5 %, systematic bias per competency, `FACTUALLY_WRONG` agreement, red-flag precision/recall.
- Trend vs previous run (deltas).
- Link: "Open full report" (opens PR comment or GCS artefact URL).

### No run yet

- `EmptyState` pointing to the `calibration-run` skill and the dataset.

### Run failed

- Inline `Alert` with the failure summary; link to CI logs.

---

## Layout

Two-column on lg+: metrics on the left, metadata on the right. Single column below.

---

## Interactions

- **Trigger a new run** — button that opens a confirmation; calls a backend endpoint that kicks off the calibration job (async). The page does not wait for completion; the user gets a toast "Run started" and can return later.

---

## Accessibility

- Metric cards are labelled (e.g., "Exact match: 0.72").
- Delta arrows have text alternatives ("up 3%" instead of just "↑").

---

## Components used

- `Card`, `Badge`, `Alert`, `Button`
- Small trend widgets (sparkline / delta) — not custom components yet; if the need grows, extract to `CalibrationMetric`
