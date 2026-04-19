# ADR-022: Non-secret defaults permitted in `.env.example`

- **Status:** Accepted
- **Date:** 2026-04-19

## Context

`.env.example` is the canonical list of environment variables required to run TechScreen. Three forces pull on its contents:

1. Constitution §5 ("No plaintext secrets") states under Enforcement: _"`.env.example` contains keys with no values."_ This is a strict reading — zero values, regardless of sensitivity.
2. ADR-013 §Storage states `.env.example` contains _"empty or placeholder values"_. This implies some values are acceptable.
3. Practical need: non-secret config defaults — enum selectors like `APP_ENV=dev`, public URLs like `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, regions like `GCP_LOCATION=europe-west1` — are genuinely useful for local bring-up. Without them, a developer must cross-reference docs for every key to discover the expected shape.

The local hook `forbid-env-values` implemented the strictest reading — blocking _any_ `KEY=value` pattern. On 2026-04-19 a commit was rejected where `.env.example` carried nine non-secret defaults that had been checked in and operated on across several sessions.

Neither reading is wrong on its own; they are inconsistent with each other. This ADR picks ADR-013's pragmatic reading and tightens enforcement to match, so the constitution, ADR-013, the hook, and the agent docs all say the same thing.

## Decision

`.env.example` may contain **non-secret defaults** alongside bare secret keys. A value is permitted if and only if it is _obviously not a credential_:

- Short enum tokens (`dev`, `mock`, `json`, `info`).
- Public URLs without embedded credentials (`http://localhost:8000`, `http://vertex-mock:8080`).
- Public identifiers — regions (`europe-west1`), placeholder domains (`no-reply@techscreen.example`).

Any line that looks credential-shaped is blocked by a regex heuristic in the `forbid-env-values` pre-commit hook. The heuristic flags:

- PEM block headers (`-----BEGIN ...`).
- JWT-shaped strings (`eyJ...`).
- URLs with inline credentials (`scheme://user:password@host`).
- Opaque strings of 32+ base64/hex-safe characters (the long-random-token shape).

`gitleaks` and `detect-secrets` remain the authoritative secret detectors. `forbid-env-values` is belt-and-suspenders on the one file most tempting to paste real config into during local bring-up.

### Reference regex

```
^\s*[A-Z0-9_]+=.*(-----BEGIN |eyJ[A-Za-z0-9_.-]{10,}|://[^:/\s@]+:[^@/\s]+@|[A-Za-z0-9+/=_-]{32,})
```

## Consequences

**Positive.**

- `.env.example` becomes self-documenting for local dev — a developer sees expected enum values, default hostnames, and placeholder domains inline.
- Constitution §5, ADR-013, the hook, and agent docs converge on a single rule.
- `gitleaks` + `detect-secrets` remain the security backstop. Relaxing the third layer does not change the "Why" of §5.

**Negative.**

- The heuristic is not infallible. A short API key (e.g. 20 chars) could slip past this hook, though `gitleaks` would likely catch known formats.
- "Non-secret" becomes a judgement call in review. Reviewers must inspect `.env.example` diffs rather than trusting "hook passed → safe".

**Mitigation.**

- `reviewer` agent checklist keeps an explicit `.env.example`-diff inspection step.
- If the heuristic proves too permissive, tighten the 32-char threshold or add `detect-secrets` with a stricter config pointed at `.env.example` specifically.

## Amendments to upstream docs

- `.specify/memory/constitution.md` §5 Enforcement line updated to reference this ADR.
- `.pre-commit-config.yaml` — `forbid-env-values` regex replaced with the heuristic above.
- `.env.example` header comment clarified (secrets empty, non-secret defaults allowed).
- `CLAUDE.md`, `docs/engineering/cloud-setup.md`, `.claude/agents/infra-engineer.md`, `.claude/agents/reviewer.md` — "no value" phrasing clarified to "empty value for secrets".
- ADR-013 already permits "placeholder values"; no amendment required there.
