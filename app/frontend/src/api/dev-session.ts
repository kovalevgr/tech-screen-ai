// Dev Session API client (T22).
//
// Hand-typed against the committed contract — see
// `specs/034-t22-dev-session-ui/contract-snapshot.yaml` (canonical copy:
// `docs/contracts/dev-session-api.yaml`) and the turn-trace row schema
// `specs/034-t22-dev-session-ui/turn-trace-snapshot.json`.
//
// Why not the generated `schema.d.ts` client: these dev-only routes land on a
// parallel backend branch, so `app/backend/openapi.yaml` does not carry them
// yet. Regenerating the repo-wide client is a separate backlog task
// (spec 034 FR-034-3); until then every type below is transcribed field-for-
// field from the contract and this is the ONLY hand-written fetch in the app.
//
// Transport matches `src/api/client.ts`: same base URL env, same
// `credentials: "include"` cookie plumbing, `globalThis.fetch` resolved per
// call so a test harness can swap it.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "./client";

// --- Contract types ---------------------------------------------------------

/** SessionView.phase — contract enum. */
export type DevPhase =
  | "INTRO"
  | "TECH"
  | "QA"
  | "CLOSE"
  | "COMPLETED"
  | "ABORTED";

/** SessionView.awaiting — who owns the next move (null = nobody). */
export type DevAwaiting = "interviewer" | "candidate" | null;

/** transcript[].role — contract enum. */
export type TranscriptRole = "interviewer" | "candidate" | "system";

export interface TranscriptMessage {
  role: TranscriptRole;
  text: string;
  turn_id: string | null;
}

export interface SessionView {
  session_id: string;
  phase: DevPhase;
  abort_reason: string | null;
  awaiting: DevAwaiting;
  competency_index: number | null;
  /** node_id → CoverageCell; the machine's own shape, serialized as-is. */
  coverage: Record<string, unknown>;
  flagged_for_review: boolean;
  /** Decimal-as-string running total from the durable ledger (T21). */
  cost_usd_total: string;
  transcript: TranscriptMessage[];
}

export interface PostTurnResult {
  /** Null when the session ended on this turn (scripted closing / abort). */
  utterance: string | null;
  session: SessionView;
}

/** turn_trace.outcome — model-call level (TraceOutcome). */
export type TraceOutcome =
  | "ok"
  | "schema_error"
  | "timeout"
  | "upstream_unavailable"
  | "budget_exceeded"
  | "config_error";

/** turn_trace.wrapper_outcome — agent-wrapper level; null for pre-T21 rows. */
export type WrapperOutcome =
  | "accepted"
  | "contract_miss_retried"
  | "rejected"
  | null;

export type TraceAgent = "interviewer" | "assessor" | "planner";

export interface TurnTraceTransition {
  phase: string;
  issued_move: string | null;
  state_before_sha: string;
  state_after_sha: string;
}

export interface TurnTraceRow {
  id: string;
  created_at: string;
  interview_session_id: string;
  turn_id: string | null;
  agent: TraceAgent;
  prompt_version: string;
  model: string;
  model_version: string | null;
  outcome: TraceOutcome;
  wrapper_outcome: WrapperOutcome;
  attempts: number;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  prompt_sha: string;
  system_prompt: string;
  user_payload: string;
  response_text: string;
  parsed: Record<string, unknown> | null;
  error_message: string | null;
  transition: TurnTraceTransition | null;
}

/**
 * PlanSnapshot — the contract defers the shape to state-machine contract §7
 * ("do not redefine, reference it"), so the client carries it opaquely and the
 * backend validates it (422 PlanInvalid).
 */
export type PlanSnapshot = Record<string, unknown>;

// --- Phase helpers ----------------------------------------------------------

export const TERMINAL_PHASES: readonly DevPhase[] = ["COMPLETED", "ABORTED"];

export function isTerminalPhase(phase: DevPhase): boolean {
  return TERMINAL_PHASES.includes(phase);
}

/** Poll cadence while the session is live (FR-034-4: "light interval poll"). */
export const DEV_SESSION_POLL_MS = 4000;

// --- Response mapping -------------------------------------------------------
//
// Required contract fields are passed through (the server guarantees them);
// nullable / optional ones are normalised to `null` so the UI never has to
// distinguish `undefined` from `null`.

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function toTranscriptMessage(raw: unknown): TranscriptMessage {
  const row = asRecord(raw);
  return {
    role: row.role as TranscriptRole,
    text: row.text as string,
    turn_id: asNullableString(row.turn_id),
  };
}

export function toSessionView(raw: unknown): SessionView {
  const row = asRecord(raw);
  return {
    session_id: row.session_id as string,
    phase: row.phase as DevPhase,
    abort_reason: asNullableString(row.abort_reason),
    awaiting: (asNullableString(row.awaiting) as DevAwaiting) ?? null,
    competency_index:
      typeof row.competency_index === "number" ? row.competency_index : null,
    coverage: asRecord(row.coverage),
    flagged_for_review: row.flagged_for_review === true,
    cost_usd_total: row.cost_usd_total as string,
    transcript: Array.isArray(row.transcript)
      ? row.transcript.map(toTranscriptMessage)
      : [],
  };
}

export function toPostTurnResult(raw: unknown): PostTurnResult {
  const row = asRecord(raw);
  return {
    utterance: asNullableString(row.utterance),
    session: toSessionView(row.session),
  };
}

function toTransition(raw: unknown): TurnTraceTransition | null {
  if (typeof raw !== "object" || raw === null) return null;
  const row = asRecord(raw);
  return {
    phase: row.phase as string,
    issued_move: asNullableString(row.issued_move),
    state_before_sha: row.state_before_sha as string,
    state_after_sha: row.state_after_sha as string,
  };
}

export function toTurnTraceRow(raw: unknown): TurnTraceRow {
  const row = asRecord(raw);
  return {
    id: row.id as string,
    created_at: row.created_at as string,
    interview_session_id: row.interview_session_id as string,
    turn_id: asNullableString(row.turn_id),
    agent: row.agent as TraceAgent,
    prompt_version: row.prompt_version as string,
    model: row.model as string,
    model_version: asNullableString(row.model_version),
    outcome: row.outcome as TraceOutcome,
    wrapper_outcome: asNullableString(row.wrapper_outcome) as WrapperOutcome,
    attempts: row.attempts as number,
    latency_ms: row.latency_ms as number,
    input_tokens: row.input_tokens as number,
    output_tokens: row.output_tokens as number,
    cost_usd: row.cost_usd as string,
    prompt_sha: row.prompt_sha as string,
    system_prompt: row.system_prompt as string,
    user_payload: row.user_payload as string,
    response_text: row.response_text as string,
    parsed:
      typeof row.parsed === "object" && row.parsed !== null
        ? asRecord(row.parsed)
        : null,
    error_message: asNullableString(row.error_message),
    transition: toTransition(row.transition),
  };
}

// --- Transport --------------------------------------------------------------

// Read at call time (not module load) so the value a test harness sets is the
// one used, exactly like the openapi-fetch client's lazy `fetch`.
function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
}

async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function devRequest(
  path: string,
  method: "GET" | "POST",
  body?: unknown
): Promise<unknown> {
  const init: RequestInit = { method, credentials: "include" };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const response = await globalThis.fetch(`${baseUrl()}${path}`, init);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `${method} ${path} failed (${response.status})`,
      await readBody(response)
    );
  }
  return response.json();
}

/** POST /api/dev/sessions — create a session from an inline PlanSnapshot. */
export async function createDevSession(
  plan: PlanSnapshot
): Promise<SessionView> {
  return toSessionView(await devRequest("/api/dev/sessions", "POST", { plan }));
}

/** POST /api/dev/sessions/{id}/turns — candidate turn → interviewer reply. */
export async function postDevTurn(
  sessionId: string,
  text: string
): Promise<PostTurnResult> {
  return toPostTurnResult(
    await devRequest(`/api/dev/sessions/${sessionId}/turns`, "POST", { text })
  );
}

/** GET /api/dev/sessions/{id} — current state view (poll target). */
export async function getDevSession(sessionId: string): Promise<SessionView> {
  return toSessionView(await devRequest(`/api/dev/sessions/${sessionId}`, "GET"));
}

/** GET /api/dev/sessions/{id}/traces — turn-trace rows, oldest first. */
export async function listDevTraces(
  sessionId: string
): Promise<TurnTraceRow[]> {
  const raw = asRecord(
    await devRequest(`/api/dev/sessions/${sessionId}/traces`, "GET")
  );
  return Array.isArray(raw.traces) ? raw.traces.map(toTurnTraceRow) : [];
}

/** True when the failure is the contract's 404 (flag off, or unknown id). */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** True when the machine refused the plan (422 PlanInvalid). */
export function isPlanInvalid(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422;
}

/** True when the turn was rejected: terminal, or not awaiting a candidate. */
export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

// --- React Query bindings ---------------------------------------------------

export const devSessionKeys = {
  all: ["dev-session"] as const,
  detail: (sessionId: string) => ["dev-session", "detail", sessionId] as const,
  traces: (sessionId: string) => ["dev-session", "traces", sessionId] as const,
};

export function useCreateDevSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (plan: PlanSnapshot) => createDevSession(plan),
    onSuccess: (view) => {
      queryClient.setQueryData(devSessionKeys.detail(view.session_id), view);
    },
  });
}

/**
 * Poll while the session is live; stop dead on the terminal phases (FR-034-4).
 *
 * `awaiting == "interviewer"` and "assessments pending" are both live states.
 * SessionView exposes no pending-assessment field (the assessor runs as a
 * background task and only shows up as coverage / cost movement), so a
 * non-terminal phase is the observable proxy for both — see spec 034
 * Clarification 4.
 */
export function sessionPollInterval(
  view: SessionView | undefined
): number | false {
  if (!view) return false;
  return isTerminalPhase(view.phase) ? false : DEV_SESSION_POLL_MS;
}

export function useDevSession(sessionId: string | null) {
  return useQuery({
    queryKey: devSessionKeys.detail(sessionId ?? ""),
    enabled: sessionId !== null,
    queryFn: () => getDevSession(sessionId as string),
    refetchInterval: (query) => sessionPollInterval(query.state.data),
  });
}

/** Traces are fetched only while the side panel is open (collapsed default). */
export function useDevTraces(
  sessionId: string | null,
  options: { enabled: boolean; poll: boolean }
) {
  return useQuery({
    queryKey: devSessionKeys.traces(sessionId ?? ""),
    enabled: sessionId !== null && options.enabled,
    queryFn: () => listDevTraces(sessionId as string),
    refetchInterval: options.poll ? DEV_SESSION_POLL_MS : false,
  });
}

export function usePostDevTurn(sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => postDevTurn(sessionId as string, text),
    onSuccess: async (result) => {
      // A poll GET issued before this turn can still be in flight; letting it
      // land after the write would briefly revert the view to the pre-turn
      // state. Cancel it first, then adopt the post-transition view the
      // machine just returned.
      await queryClient.cancelQueries({
        queryKey: devSessionKeys.detail(result.session.session_id),
      });
      queryClient.setQueryData(
        devSessionKeys.detail(result.session.session_id),
        result.session
      );
      if (sessionId !== null) {
        queryClient.invalidateQueries({
          queryKey: devSessionKeys.traces(sessionId),
        });
      }
    },
  });
}
