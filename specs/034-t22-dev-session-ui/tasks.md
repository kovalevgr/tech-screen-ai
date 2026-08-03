# Tasks — 034 T22 dev UI

- [x] T001 Commit spec kit + contract-snapshot.yaml (verbatim)
- [x] T002 API client + hand-typed contract types (no schema.d.ts regen)
- [x] T003 `/dev/session` page: plan form → create; chat thread with role styling; input gated by awaiting; DEV ONLY banner
- [x] T004 Header: phase / competency / cost_usd_total / flagged badge; terminal + flag-disabled screens
- [x] T005 Trace side panel (collapsible, pretty JSON, outcome vs wrapper_outcome distinction)
- [x] T006 Polling loop per FR-034-4
- [x] T007 jest: client mapping, awaiting gating, trace panel, terminal states
- [x] T008 eslint + tsc + jest + format green; diff confined to app/frontend/** + specs/034; do NOT push until told

Gates run locally 2026-08-03: eslint (0 warnings), `tsc --noEmit`, `pnpm test`
(7 suites / 51 tests), `pnpm tokens:check`, `pnpm lint:visual-discipline` — all
green. Branch is committed but NOT pushed, per T008.
