# Motion

Durations, easings, and reduced-motion behaviour. Motion communicates causation; we do not use it to decorate.

---

## Durations

| Token | Value | Use |
| --- | --- | --- |
| `motion.instant` | 0 ms | Toggles where no transition helps understanding |
| `motion.fast` | 100 ms | Button press feedback, chip toggle |
| `motion.base` | 150 ms | Default transition for hover / focus / state change |
| `motion.medium` | 200 ms | Entering / leaving elements |
| `motion.slow` | 300 ms | Page transitions, large panel slide-in |

Anything longer than 300 ms is a bug. The candidate should never wait on a transition to reach content.

---

## Easings

| Token | Value | Use |
| --- | --- | --- |
| `ease.standard` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | Default for most transitions |
| `ease.emphasised` | `cubic-bezier(0.3, 0, 0, 1)` | Entering / arriving content |
| `ease.exit` | `cubic-bezier(0.4, 0, 1, 1)` | Leaving content (quicker tail) |

No `ease-linear` except for loading spinners. No bouncing / overshoot curves.

---

## Default patterns

- **Hover / focus state change:** 150 ms, `ease.standard`. Colour + shadow only; no translate.
- **Button press:** 100 ms scale to 0.98, `ease.standard`. Returns on release.
- **Modal open:** 200 ms fade + 8 px upward translate, `ease.emphasised`.
- **Modal close:** 150 ms fade, `ease.exit`. No translate (the scrim darkening is the departure signal).
- **Toast enter:** 200 ms slide-in from top, `ease.emphasised`.
- **Panel expand / collapse:** 200 ms height + opacity, `ease.standard`.
- **Skeleton shimmer:** 1500 ms linear loop. Disabled under `prefers-reduced-motion`.

---

## Reduced motion

When the user sets `prefers-reduced-motion: reduce`:

- All translate / scale / rotation transitions become opacity-only.
- Durations fall back to `motion.fast` (100 ms).
- Skeleton shimmer stops — a solid muted background is used instead.
- Spinners continue, but slower (2 s rotation instead of 1 s).

This is enforced in the base `globals.css`:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 100ms !important;
    transition-duration: 100ms !important;
    transition-property: opacity, color, background-color, border-color !important;
  }
}
```

Components that need to override this (rare) set `data-motion="ok"` on the element; the CSS selector above excludes them.

---

## What we do not do

- Parallax scrolling.
- Scroll-triggered showreels.
- Auto-playing hero animations.
- Elastic / bouncing overshoot.
- Anything that implies "gamified" progression (confetti, pulsating CTAs).

---

## Export

`tokens.ts` exports the `motion` object. Tailwind picks up durations under `transitionDuration` and easings under `transitionTimingFunction`.

## Document versioning

- v1.1 — 2026-04-19. Reviewed against the Chat-iX reference; no changes. The reference product has no animated chrome, matching this spec.
- v1.0 — 2026-04-18. Initial motion tokens.
