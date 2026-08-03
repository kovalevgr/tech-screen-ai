# Feature spec — T22 Dev Conversation UI

**Status**: Draft · **Branch**: `034-t22-dev-session-ui` · **Authored by**: main loop (policy rev. 2)
**Contract**: [`docs/contracts/dev-session-api.yaml`](../../docs/contracts/dev-session-api.yaml) — consumed as-is; the backend half lands on the parallel `033` branch.

## What / why

Internal `/dev/session` page so the team can drive a full mock interview end-to-end and see what the system sees: chat with the Interviewer + collapsible side panel with raw turn-trace JSON per turn. Dev-only; explicitly NOT on the Chat-iX design baseline (excluded from design gates per the implementation plan).

## Functional requirements

- **FR-034-1** Page `/dev/session` in the existing Next.js App Router: plan input (JSON textarea prefilled with a valid demo PlanSnapshot), create-session button, chat thread (system/interviewer/candidate roles), message input enabled only when `awaiting == "candidate"`, phase/coverage/cost header, flagged_for_review badge.
- **FR-034-2** Side panel: per-turn trace list from `GET .../traces`, collapsed by default, raw JSON pretty-printed; `wrapper_outcome`/`outcome` visually distinguished (ok vs rejected).
- **FR-034-3** API client: hand-typed thin fetch wrapper matching the contract exactly (types transcribed from the YAML — do NOT regenerate the repo-wide `schema.d.ts`; that stays a separate backlog task). Base path relative; auth header plumbing reuses whatever the existing frontend API layer does.
- **FR-034-4** Polling: after posting a turn, refresh SessionView; light interval poll (e.g. 3–5 s) while `awaiting == "interviewer"` or assessments pending; stop on terminal phases. No WebSocket in this task (real WS is T29a — do not invent a protocol).
- **FR-034-5** Terminal states rendered honestly: COMPLETED (closing text) and ABORTED with reason. 404-when-flag-off surfaced as a clear "dev API disabled (enable_live_orchestrator)" screen, not a crash.
- **FR-034-6** Tests per existing frontend conventions (jest): client mapping, state rendering (awaiting gating of the input), trace panel rendering, terminal states. Mock fetch; no live backend in CI.

## Clarifications (decided — do not reopen)

1. Backend routes do not exist on this branch — the two streams merge independently (033 first). The UI is built and tested against the CONTRACT with mocked fetch; the first live run happens post-merge (T23 window).
2. Minimal styling with existing Tailwind primitives; no design-system components required; page carries a visible "DEV ONLY" banner.
3. No candidate PII concerns: dev sessions use synthetic plans/answers typed by the team.

### Implementation notes (frontend stream, recorded during implementation)

Open details resolved to the simplest option consistent with the contract. No design decision was reopened.

4. **Poll condition.** FR-034-4 names two live conditions (`awaiting == "interviewer"`, assessments pending). `SessionView` carries no pending-assessment field — the assessor runs as a background task and only shows up as coverage / cost movement — so the observable proxy for both is "phase is not terminal". `sessionPollInterval()` returns 4 s while the phase is non-terminal and `false` on `COMPLETED` / `ABORTED`; the traces query uses the same cadence while the panel is open.
5. **Transport.** The hand-typed client mirrors `src/api/client.ts`: same `NEXT_PUBLIC_API_BASE_URL` base (relative when unset), `credentials: "include"` cookie plumbing (the frontend has no bearer-token layer today), `globalThis.fetch` resolved per call, failures thrown as the existing `ApiError` so status branching (404 / 409 / 422) matches the rest of the app. Contract paths are used verbatim, including their `/api` prefix.
6. **Copy.** Page chrome is English — this is an internal debug console, not a candidate surface; the Ukrainian on screen is what the machine produced (transcript) or what the demo plan carries. The candidate-facing i18n files are untouched.
7. **Styling.** Plain HTML elements plus token-backed Tailwind utilities; no `components/ui/*` primitive is imported, per the T22 design-gate exclusion. The page still satisfies the repo's visual-discipline hooks: no raw hex, no arbitrary bracket values, no `dark:`, no shadows, no decorative animation.
8. **`utterance` vs transcript.** The thread renders `SessionView.transcript` as the single source of truth; the `utterance` field of the last `POST /turns` response is echoed verbatim under the composer, including its meaningful `null` ("the session ended on this turn"), rather than being dropped as redundant.
9. **404 screen.** The contract returns 404 both for a disabled flag and for an unknown session, and the response cannot distinguish them, so the notice names both causes and points at `enable_live_orchestrator`.
10. **Traces panel.** Collapsed by default means no request at all: the traces query is disabled until the panel is opened; afterwards it is invalidated on every posted turn and polled on the same cadence while the session is live. Each row shows `outcome` and `wrapper_outcome` as two separately labelled chips, since `outcome=ok` + `wrapper_outcome=rejected` is a real combination.
11. **Plan input.** The textarea checks JSON syntax client-side only (obvious typo, no round trip); semantic validation stays with the machine and its 422 `PlanInvalid` is surfaced as-is.

## Success criteria

- SC-1 jest green; eslint/tsc green; no design-gate checks demanded.
- SC-2 Diff touches ONLY `app/frontend/**` + `specs/034-…` (zero backend/openapi/config files — the 033 stream owns those; this guarantees conflict-free parallel merge).
- SC-3 A reviewer reading the page code can trace every displayed field to a contract field.
