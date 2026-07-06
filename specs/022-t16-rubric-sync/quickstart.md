# Quickstart — T16 operator runbook + live acceptance sweep

Branch-local checks (pytest subset + pre-commit) are already green in the PR. Everything below needs the live project and is the operator's post-merge sweep. **Nothing here was executed from the implementation branch** — the sweep starts after merge to `main`.

Prerequisite: branch `019-cloud-sql-idle` merged (supplies `scripts/cloud-sql-power.sh`; research R8). If it is not, substitute `gcloud sql instances patch techscreen-pg[-dev] --activation-policy=ALWAYS|NEVER` for the wake/sleep calls.

## 1. Wake the instances (cost-idle mode)

```bash
scripts/cloud-sql-power.sh status
scripts/cloud-sql-power.sh wake all          # ~60–90 s until RUNNABLE
```

## 2. Apply the extended grants (once per instance)

As `techscreen_migrator` via the Auth Proxy (same procedure as T06 quickstart § 7 — proxy to each instance in turn):

```bash
psql 'postgresql://techscreen_migrator:<pw>@127.0.0.1:5432/techscreen' \
  -f scripts/cloud-db-grants.sql              # re-runnable; GRANT is idempotent
```

Verify: `\dp rubric_tree_version` shows the IAM user with `ar` (INSERT+SELECT) — and `\dp turn_trace` shows it **nowhere**.

## 3. Terraform no-op check (one cosmetic diff expected)

```bash
terraform -chdir=infra/terraform plan
```

Expected: exactly one in-place update — `google_service_account.flag_sync` `description` (text no longer claims feature_flag-only privileges). Apply it.

## 4. First live run — benign no-op

Trigger **Sync configs-as-code** via `workflow_dispatch` on `main` (or merge any rubric touch). Expected: all four legs green; `sync-rubric` legs report either `created rubric_tree_version …` (first seed of `configs/rubric/example.yaml`) or `no-op: payload hash … matches` on repeat runs. Confirm per environment:

```sql
SELECT label, payload_hash FROM rubric_tree_version ORDER BY created_at DESC LIMIT 1;
SELECT action, subject_hash FROM audit_log WHERE action = 'rubric.versioned' ORDER BY created_at DESC LIMIT 1;
```

## 5. Destructive gate — negative then positive (SC-002)

1. Open a PR that sets `retired: true` on the `example.demonstration` node's sibling — or simpler, edits a `descriptor_en` once real content exists; for the demo file, flip the *file-level* `retired:` to `true`. PR body **without** any `ADR-xxx`. Merge. Expected: both `sync-rubric` legs fail at "Destructive-change gate" (before WIF auth) with a `NODE_RETIRED` annotation; `sync-feature-flags` legs unaffected (SC-004).
2. Revert-merge (or follow-up) with `ADR-018` cited in the PR body. Expected: gate passes with a `::notice::… authorised by citation` annotation, seed applies a new version.

## 6. Forbidden removal (SC-003)

In a scratch PR, delete the `example.demonstration` node outright, cite any ADR in the body, merge. Expected: gate exits 2 with `NODE_REMOVED` + retire-then-introduce guidance regardless of the citation. Restore via revert.

## 7. Cost-idle failure path (SC-007)

```bash
scripts/cloud-sql-power.sh sleep dev
```

Re-run the workflow (`workflow_dispatch`). Expected: `sync-rubric (dev)` passes the gate, then fails at the seed step within ~20–60 s; the `::error::` names `scripts/cloud-sql-power.sh wake dev`; the prod leg is green. Then: wake dev, use **Re-run failed jobs**, confirm the leg goes green.

## 8. Sleep everything

```bash
scripts/cloud-sql-power.sh sleep all
scripts/cloud-sql-power.sh status
```

## 9. Record

Paste per-step results into the PR acceptance table (SC-001…SC-007), same convention as the T06 sweep.
