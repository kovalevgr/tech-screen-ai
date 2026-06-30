// Typed API client for the TechScreen backend.
//
// A single `openapi-fetch` client, typed by the generated `schema.d.ts`
// (regenerate via `pnpm gen:api` whenever app/backend/openapi.yaml changes).
// All UI data access goes through this client — never a hand-written fetch
// (frontend-engineer convention; constitution §14 contract-first).
//
// `credentials: "include"` sends the session cookie (real SSO is T07; until
// then the client still attaches credentials so the auth seam is in place).
// The base URL is the build-time public env; in tests MSW intercepts the
// resulting absolute URL.

import createClient from "openapi-fetch";

import type { paths } from "./schema";

// NEXT_PUBLIC_API_BASE_URL is inlined at build time. Fall back to a relative
// base in case it is unset so requests stay same-origin rather than throwing.
const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export const apiClient = createClient<paths>({
  baseUrl,
  credentials: "include",
  // Resolve `fetch` lazily per call rather than capturing the reference at
  // client-construction time. This keeps the client working when a test
  // harness (MSW) swaps `globalThis.fetch` after this module has loaded.
  fetch: (...args) => globalThis.fetch(...args),
});

// A discriminated error surfaced from a failed request, carrying the HTTP
// status so callers can map 401/403/404/422 to the right UI state.
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}
