# ADR-016: Auth split — Workspace SSO internal, magic link candidates

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen has two user audiences with incompatible auth requirements:

- **Internal users** (recruiters, reviewers, admins) — N-iX employees with Google Workspace accounts. They need SSO, minimal friction, and group-based RBAC.
- **Candidates** — external people invited once or twice. They should not be forced to create an account, remember a password, or share credentials with anyone.

A single auth system covering both audiences would require Identity Platform or similar, with more moving parts and cost.

## Decision

Two separate auth paths:

### Internal users

- Google Workspace OAuth 2.0.
- Only `@n-ix.com` emails accepted (or configured org domain allow-list).
- Role assignment via DB table `user_role` — not via Workspace groups at MVP.
- Session: HTTP-only secure cookie signed with a key from Secret Manager.

### Candidates

- **Magic link** sent by email. Single-use, short-lived (configurable, default 24 h).
- Table `magic_token (token_hash, candidate_id, purpose, expires_at, consumed_at)`.
- Token is a cryptographically random 32-byte value, base64url-encoded. Only the **hash** is stored in the DB; the raw token appears only in the email body.
- Consumed tokens remain in the table for audit, marked `consumed_at`.
- No candidate password, no candidate account, no candidate session beyond the single interview.

## Consequences

**Positive.**

- Candidates hit "join interview" with zero cognitive overhead.
- Internal security posture leans on existing Workspace SSO — no second password store to protect.
- No Identity Platform bill.

**Negative.**

- Email deliverability becomes a critical path: a magic link that lands in spam is a blocked candidate.
- Magic link emails are a phishing-shaped target — the sending domain and template must be unmistakable.

**Mitigation.**

- Use a reputable transactional email provider (SendGrid / Postmark) with DKIM, SPF, and DMARC properly configured for the sender domain.
- Email template is visually consistent with N-iX brand, sent from a dedicated subdomain (e.g. `screen.n-ix.com`), and explicitly names the recipient and the role they applied to.
