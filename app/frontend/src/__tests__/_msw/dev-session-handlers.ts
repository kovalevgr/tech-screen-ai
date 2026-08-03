// MSW handlers + fixtures for the dev session API (spec 034).
//
// Kept apart from the position-template handlers so the dev console tests own
// their own in-memory session and cannot perturb the existing suites. Every
// payload here is shaped by the contract snapshot
// (specs/034-t22-dev-session-ui/contract-snapshot.yaml and
// turn-trace-snapshot.json), so a contract change breaks the fixtures first.

import { http, HttpResponse } from "msw";

import type { SessionView, TurnTraceRow } from "@/api/dev-session";

export const DEV_SESSION_ID = "8f14e45f-ceea-467a-9c1a-1f4b3f0d1111";
export const DEV_TURN_ID = "8f14e45f-ceea-467a-9c1a-1f4b3f0d2222";

const CREATE = "*/api/dev/sessions";
const ITEM = "*/api/dev/sessions/:sessionId";
const TURNS = "*/api/dev/sessions/:sessionId/turns";
const TRACES = "*/api/dev/sessions/:sessionId/traces";

export function sessionViewFixture(
  overrides: Partial<SessionView> = {}
): SessionView {
  return {
    session_id: DEV_SESSION_ID,
    phase: "TECH",
    abort_reason: null,
    awaiting: "candidate",
    competency_index: 0,
    coverage: {
      "py.async": { best_level: 3, best_confidence: 0.8, latest_level: 3 },
    },
    flagged_for_review: false,
    cost_usd_total: "0.041200",
    transcript: [
      { role: "system", text: "Вітаємо! Готові почати?", turn_id: null },
      {
        role: "interviewer",
        text: "Розкажіть, як працює event loop в asyncio.",
        turn_id: DEV_TURN_ID,
      },
    ],
    ...overrides,
  };
}

export function traceRowFixture(
  overrides: Partial<TurnTraceRow> = {}
): TurnTraceRow {
  return {
    id: "8f14e45f-ceea-467a-9c1a-1f4b3f0d3333",
    created_at: "2026-08-03T10:00:00Z",
    interview_session_id: DEV_SESSION_ID,
    turn_id: DEV_TURN_ID,
    agent: "interviewer",
    prompt_version: "v0004",
    model: "gemini-2.5-pro",
    model_version: "gemini-2.5-pro-001",
    outcome: "ok",
    wrapper_outcome: "accepted",
    attempts: 1,
    latency_ms: 1840,
    input_tokens: 1200,
    output_tokens: 310,
    cost_usd: "0.004100",
    prompt_sha: "b4c1d2e3f4a5b6c7",
    system_prompt: "You are the Interviewer…",
    user_payload: '{"phase":"TECH"}',
    response_text: '{"utterance_uk":"…"}',
    parsed: { internal_move_executed: "ask_seed" },
    error_message: null,
    transition: {
      phase: "TECH",
      issued_move: "ask_seed",
      state_before_sha: "aaa111",
      state_after_sha: "bbb222",
    },
    ...overrides,
  };
}

/**
 * A stateful handler set for one dev session: create returns `initial`, GET
 * returns the current view, POST /turns hands the typed text to `onTurn` and
 * adopts whatever session it returns (so a test can script the machine's
 * answer), and GET /traces returns `traces`.
 */
export function devSessionHandlers(config: {
  initial: SessionView;
  onTurn?: (
    text: string,
    current: SessionView
  ) => { utterance: string | null; session: SessionView };
  traces?: TurnTraceRow[];
}) {
  let current = config.initial;
  return [
    http.post(CREATE, () => HttpResponse.json(current, { status: 201 })),
    http.get(ITEM, () => HttpResponse.json(current)),
    http.post(TURNS, async ({ request }) => {
      const body = (await request.json()) as { text: string };
      const result = config.onTurn?.(body.text, current) ?? {
        utterance: null,
        session: current,
      };
      current = result.session;
      return HttpResponse.json(result);
    }),
    http.get(TRACES, () =>
      HttpResponse.json({ traces: config.traces ?? [] })
    ),
  ];
}

/** Every dev route answers `status` — e.g. 404 when the flag is off. */
export function devSessionStatusHandlers(status: number) {
  const fail = () => HttpResponse.json({ detail: "error" }, { status });
  return [
    http.post(CREATE, fail),
    http.get(ITEM, fail),
    http.post(TURNS, fail),
    http.get(TRACES, fail),
  ];
}
