# Quickstart — Validating the T03 PR

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contract**: [contracts/frontend-contract.md](./contracts/frontend-contract.md)
**Audience**: Human reviewer or `reviewer` sub-agent validating the T03 PR before merge.
**Target time**: under 5 minutes end-to-end (after the first image build, which takes ~90 s).

Constitution §7 says dev = CI = prod containers; **this walkthrough exercises the canonical Docker loop only.** No native `pnpm --dir app/frontend …` step appears below. If a step fails because Docker is not running, treat that as a hard precondition error rather than a T03 acceptance failure.

---

## Prerequisites (one-time per machine)

- **Docker Engine 24.x or Docker Desktop** running locally. `docker --version` and `docker compose version` both succeed.
- **`pre-commit` ≥ 3.7.0** installed on the host (T01 baseline) — the only host tool the canonical loop needs, and only because pre-commit hooks fire from `git commit`.
- `git` and `curl` (for the chrome smoke).

No GCP credentials, no backend running, no Postgres, no Vertex needed for T03 — frontend boots without external dependencies (FR-003) and profiles gate everything else.

---

## Step 1 — Check out the PR branch

```bash
git fetch origin
git switch 006-t03-nextjs-skeleton
git status --short            # expect: clean tree
```

## Step 2 — Build the dev image

```bash
docker compose --profile web build frontend
```

**Expected**: image builds successfully. First run is ~90 s (downloads `node:20-bookworm-slim`, runs `pnpm install --frozen-lockfile`, copies sources). Subsequent runs hit the layer cache and finish in <5 s. The image targets the `dev` stage of the multi-stage Dockerfile — Jest, RTL, ESLint, TS, and `tsx` are all bundled.

## Step 3 — Start the frontend and hit `/`

```bash
docker compose --profile web up -d frontend           # detached so we can curl from the same shell
curl -sS -o /tmp/t03.html -w "%{http_code}\n" http://127.0.0.1:3000/
docker compose --profile web down                     # stop + clean up
```

**Expected**: HTTP 200 plus an HTML body containing the N-iX wordmark, a sidebar nav stub, and the content slot. Open the URL in a browser to visually confirm the chrome matches `docs/design/references/hellow_page.png`: white canvas, `surface.raised` left sidebar, 1-px subtle dividers, brand-orange wordmark in the top bar, neutral typography on white.

The container hot-reloads on source changes thanks to the `app/frontend` bind-mount in `docker-compose.yml`, so a follow-up `curl` after editing `top-bar.tsx` shows the new behaviour without a rebuild.

## Step 4 — Run the frontend test suite in container

```bash
docker compose -f docker-compose.test.yml run --rm --build frontend pnpm test
```

**Expected**: pnpm runs Jest. Two tests pass:

- `app/frontend/src/__tests__/shell.test.tsx` — admin-shell render + keyboard tab + focus ring (FR-011).
- `app/frontend/src/__tests__/tokens.test.ts` — design-token drift check (FR-006).

Wall time under 60 s on a clean tree (SC-002), excluding image build.

## Step 5 — Run the token-drift check

```bash
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
```

**Expected**: exit code 0, no output (silent success — the on-disk `tokens.ts` and the marker-bracketed region of `globals.css` match what the generator produces from `docs/design/tokens/*.md`). Wall time < 5 s (SC-003).

To deliberately exercise the failure path:

```bash
# Mutate one row in the markdown source...
sed -i '' 's/`#E8573C`/`#FF0000`/' docs/design/tokens/colors.md
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
# Expect: exit code 1, unified-diff head identifying the brand.primary role.
git checkout -- docs/design/tokens/colors.md          # revert before continuing
```

## Step 6 — Run the visual-discipline check

```bash
pre-commit run visual-discipline --all-files
```

**Expected**: exit code 0, hook reports "Passed". Wall time < 5 s on the post-T03 tree (SC-004).

To deliberately exercise the failure path (raw-hex case):

```bash
echo 'export const oops = "#ff0000";' > app/frontend/src/oops.ts
pre-commit run visual-discipline --all-files
# Expect: exit code 1; output names app/frontend/src/oops.ts:1 and the offending hex.
rm app/frontend/src/oops.ts
```

To exercise the `dark:` failure path:

```bash
echo 'export const oops = "dark:bg-red-500";' > app/frontend/src/oops.ts
pre-commit run visual-discipline --all-files
# Expect: exit code 1; output names app/frontend/src/oops.ts:1.
rm app/frontend/src/oops.ts
```

## Step 7 — Run the lint and type check

```bash
docker compose -f docker-compose.test.yml run --rm frontend pnpm run lint
```

**Expected**: exit code 0 (FR-014, SC-008). The eslint config extends `next/core-web-vitals` plus the existing T01 rules; tsc runs in `--noEmit` mode (the config from T01 is unchanged). The `lint` script chains both — `eslint . --max-warnings=0 && tsc --noEmit` — under pnpm so `node_modules/.bin` is on PATH for both binaries.

## Step 8 — Confirm the no-host pre-commit baseline still works

```bash
pre-commit run --all-files
```

**Expected**: exit code 0. Confirms gitleaks, detect-secrets, forbid-env-values, eslint, ruff, the frontend `eslint` hook, and the two new T03 hooks (`visual-discipline`, `tokens-drift`) all pass on the clean tree (FR-014, FR-016).

---

## Step 9 — Diff-walk the PR

The reviewer should be able to walk the diff and confirm:

| Confirmation                                                                                                                                            | Where to look                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Chrome lives in the **root** layout, not in `page.tsx`                                                                                                  | `app/frontend/src/app/layout.tsx`                                                                              |
| Top bar contains the N-iX wordmark in brand orange                                                                                                      | `app/frontend/src/components/shell/top-bar.tsx`                                                                 |
| Sidebar nav items are focusable                                                                                                                         | `app/frontend/src/components/shell/sidebar.tsx`                                                                 |
| `tokens.ts` is generated (carries a "DO NOT EDIT" comment at the top)                                                                                   | `app/frontend/src/design/tokens.ts`                                                                            |
| `globals.css` has `/* TOKENS:START */` … `/* TOKENS:END */` markers                                                                                     | `app/frontend/src/app/globals.css`                                                                             |
| Tailwind theme: colours/radii/typography/motion via `theme.extend`; spacing OVERRIDDEN                                                                  | `app/frontend/tailwind.config.ts`                                                                              |
| Nine shadcn primitives committed under `components/ui/`                                                                                                 | `app/frontend/src/components/ui/`                                                                              |
| `components.json` matches the contract (`style: new-york`, `baseColor: neutral`, `cssVariables: true`, `iconLibrary: lucide`)                            | `app/frontend/components.json`                                                                                  |
| Two new pre-commit hooks: `visual-discipline` + `tokens-drift`                                                                                          | `.pre-commit-config.yaml`                                                                                      |
| `Dockerfile.frontend` ships `base/deps/dev/build/runtime` stages                                                                                        | `Dockerfile.frontend`                                                                                          |
| `docker-compose.yml` `frontend` service uses `target: dev`; `depends_on.backend` is `required: false`                                                   | `docker-compose.yml`                                                                                           |
| `docker-compose.test.yml` adds a `frontend` service block targeting `dev`                                                                               | `docker-compose.test.yml`                                                                                      |
| README has a "Frontend dev loop (Docker-first)" subsection                                                                                              | `README.md`                                                                                                    |
| `app/frontend/tooling.d.ts` is **deleted** (its purpose — placeholder until real sources exist — is fulfilled)                                          | `app/frontend/` (file should not exist)                                                                        |
| `app/frontend/src/messages/{uk,en}.json` exist with the demo key + `README.md` explains they are markers                                                | `app/frontend/src/messages/`                                                                                    |
| Zero `dark:` Tailwind variants anywhere in `app/frontend/src/`                                                                                          | `rg -n '\bdark:[a-z]' app/frontend/src/` returns nothing                                                       |
| Zero raw hex values outside `tokens.ts` and the `globals.css` marker region                                                                             | `app/frontend/scripts/check-visual-discipline.sh` succeeds                                                     |

If every row in this table holds and Steps 1–8 all pass, T03 is ready to merge. The reviewer does NOT need to read the implementation code beyond confirming the diff scope matches FR-013 (no auth, no real screens, no OpenAPI client, no `dark:`, no motion, no analytics).

---

## What to do if a step fails

1. **Step 2 fails (image build)**: check `Dockerfile.frontend` exists; check `app/frontend/package.json` and `pnpm-lock.yaml` are committed; check `engines.node` and `packageManager` are set.
2. **Step 3 fails (HTTP 200 but no chrome)**: open the rendered HTML in a browser; if the wordmark is missing, the chrome is in `page.tsx` instead of `layout.tsx` — surfaces 1 of `frontend-contract.md` violated.
3. **Step 4 fails (test failure)**: read the diff head from Jest. If `shell.test.tsx` fails, the chrome shape regressed; if `tokens.test.ts` fails, someone hand-edited `tokens.ts` or the `TOKENS:START`…`TOKENS:END` block of `globals.css`.
4. **Step 5 fails (drift)**: run `pnpm tokens:generate` to regenerate; commit the result. If markdown was the source of the drift, that's expected and fine.
5. **Step 6 fails (visual discipline)**: ripgrep prints the offending file:line. Replace the raw hex with a token role (or move it to `tokens.ts` if it really is a new token, in which case extend the markdown first).
6. **Step 7 fails (lint or tsc)**: ordinary lint/type errors. Fix them.
7. **Step 8 fails (host pre-commit)**: typically gitleaks or detect-secrets. Confirm no `.env` content was accidentally committed.
