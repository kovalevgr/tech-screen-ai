# Feature flags

The human-readable index for every feature flag the project has ever had. The
machine-readable source of truth is [`configs/feature-flags.yaml`](../../configs/feature-flags.yaml);
the contract its entries must conform to is
[`docs/contracts/feature-flag.schema.json`](../contracts/feature-flag.schema.json).
A bidirectional pre-commit + CI hook
([`scripts/check-feature-flag-registration.py`](../../scripts/check-feature-flag-registration.py))
keeps the three artefacts (plus the in-code call sites under `app/backend/`)
consistent on every commit.

## How to

### Declare a new flag
1. Add an entry to `configs/feature-flags.yaml` with `state: active`,
   `default: false`, an owner (your `@gh-handle`), and a one-line description.
2. Add **at least one** `is_enabled("your_flag_name")` call site in `app/backend/`.
3. Add a row to the **Active flags** table below (name, owner, default,
   description).
4. Commit and open a PR. After merge to `main`, the post-merge workflow
   ([`.github/workflows/sync-feature-flags.yml`](../../.github/workflows/sync-feature-flags.yml))
   creates a `feature_flag` row with `enabled=false`, `updated_by='configs-as-code'`.

### Flip a flag (enable in production)
1. Open a PR that sets `default: true` for the entry (mostly documentation —
   the live `enabled` column is what matters).
2. Merge. The post-merge workflow upserts the row; the next `is_enabled` call
   on every running backend instance reflects the new value **within ~1 second**
   (LISTEN/NOTIFY).

### Sunset a flag (retire the last call site)
1. Remove every `is_enabled("name")` call from `app/backend/` in your PR.
2. In `configs/feature-flags.yaml`, change `state: active` → `state: sunset`
   and set both `sunset_pr` (the PR back-reference, e.g. `"#123"`) and
   `sunset_date` (`YYYY-MM-DD`).
3. **Move** the row from the Active table to the Sunset table below. Do not
   delete it — sunset entries stay forever (constitution §1).

### Emergency disable (operator)
1. Connect to the production database with the `techscreen_app` role
   credentials and run:
   `UPDATE feature_flag SET enabled = false, updated_by = '<your-handle>' WHERE name = '<flag>';`
2. The change propagates to every backend instance in **under 1 second**
   (FR-003).
3. Open a follow-up PR to reconcile `configs/feature-flags.yaml` (set
   `default: false` or sunset the flag), so the post-merge workflow's orphan
   check stays clean.

## Active flags

| name | owner | default | description |
| ---- | ----- | ------- | ----------- |

*(none yet — T05a ships the mechanism; the first real flag will land with
its consuming Tier-3+ feature.)*

## Sunset flags

| name | sunsetted in | date | description |
| ---- | ------------ | ---- | ----------- |
| example_demonstration | #9 | 2026-04-28 | Demonstration entry showing the sunset-row shape; never wired to a call site, never re-introduced. |
