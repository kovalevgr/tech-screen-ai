// T22 — dev session API client (FR-034-3, FR-034-6).
//
// Asserts the hand-typed client against the contract snapshot: the paths and
// bodies it sends, and how it maps responses (nullable fields → null, arrays →
// arrays, HTTP failures → ApiError with the status the UI branches on).
// Network is MSW-mocked; no live backend.

import { http, HttpResponse } from "msw";

import { ApiError } from "@/api/client";
import {
  createDevSession,
  getDevSession,
  isConflict,
  isNotFound,
  isPlanInvalid,
  isTerminalPhase,
  listDevTraces,
  postDevTurn,
} from "@/api/dev-session";
import {
  DEV_SESSION_ID,
  devSessionHandlers,
  devSessionStatusHandlers,
  sessionViewFixture,
  traceRowFixture,
} from "@/__tests__/_msw/dev-session-handlers";
import { server } from "@/__tests__/_msw/server";

describe("dev session client — requests", () => {
  it("POSTs the plan wrapped in { plan } to /api/dev/sessions", async () => {
    const seen: { url: string; body: unknown } = { url: "", body: null };
    server.use(
      http.post("*/api/dev/sessions", async ({ request }) => {
        seen.url = request.url;
        seen.body = await request.json();
        return HttpResponse.json(sessionViewFixture(), { status: 201 });
      })
    );

    const view = await createDevSession({ plan_version: 1 });

    expect(seen.url).toContain("/api/dev/sessions");
    expect(seen.body).toEqual({ plan: { plan_version: 1 } });
    expect(view.session_id).toBe(DEV_SESSION_ID);
  });

  it("POSTs { text } to /api/dev/sessions/{id}/turns", async () => {
    const seen: { url: string; body: unknown } = { url: "", body: null };
    server.use(
      http.post("*/api/dev/sessions/:sessionId/turns", async ({ request }) => {
        seen.url = request.url;
        seen.body = await request.json();
        return HttpResponse.json({
          utterance: "Дякую, продовжимо.",
          session: sessionViewFixture(),
        });
      })
    );

    const result = await postDevTurn(DEV_SESSION_ID, "моя відповідь");

    expect(seen.url).toContain(`/api/dev/sessions/${DEV_SESSION_ID}/turns`);
    expect(seen.body).toEqual({ text: "моя відповідь" });
    expect(result.utterance).toBe("Дякую, продовжимо.");
    expect(result.session.phase).toBe("TECH");
  });

  it("GETs the session view from /api/dev/sessions/{id}", async () => {
    let seenUrl = "";
    server.use(
      http.get("*/api/dev/sessions/:sessionId", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json(sessionViewFixture({ phase: "QA" }));
      })
    );

    const view = await getDevSession(DEV_SESSION_ID);

    expect(seenUrl).toContain(`/api/dev/sessions/${DEV_SESSION_ID}`);
    expect(view.phase).toBe("QA");
  });
});

describe("dev session client — response mapping", () => {
  it("maps a SessionView, defaulting the absent nullable fields to null", async () => {
    server.use(
      http.get("*/api/dev/sessions/:sessionId", () =>
        // A minimal payload: the contract's optional keys are simply absent.
        HttpResponse.json({
          session_id: DEV_SESSION_ID,
          phase: "INTRO",
          awaiting: null,
          coverage: {},
          flagged_for_review: false,
          cost_usd_total: "0.000000",
          transcript: [{ role: "system", text: "Вітаємо!", turn_id: null }],
        })
      )
    );

    const view = await getDevSession(DEV_SESSION_ID);

    expect(view).toEqual({
      session_id: DEV_SESSION_ID,
      phase: "INTRO",
      abort_reason: null,
      awaiting: null,
      competency_index: null,
      coverage: {},
      flagged_for_review: false,
      cost_usd_total: "0.000000",
      transcript: [{ role: "system", text: "Вітаємо!", turn_id: null }],
    });
  });

  it("keeps abort_reason and a null utterance from a terminating turn", async () => {
    const aborted = sessionViewFixture({
      phase: "ABORTED",
      abort_reason: "cost_ceiling",
      awaiting: null,
    });
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture(),
        onTurn: () => ({ utterance: null, session: aborted }),
      })
    );

    const result = await postDevTurn(DEV_SESSION_ID, "…");

    expect(result.utterance).toBeNull();
    expect(result.session.phase).toBe("ABORTED");
    expect(result.session.abort_reason).toBe("cost_ceiling");
    expect(isTerminalPhase(result.session.phase)).toBe(true);
  });

  it("maps trace rows, including the outcome / wrapper_outcome pair", async () => {
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture(),
        traces: [
          traceRowFixture(),
          traceRowFixture({
            id: "8f14e45f-ceea-467a-9c1a-1f4b3f0d4444",
            agent: "assessor",
            outcome: "ok",
            wrapper_outcome: "rejected",
            parsed: null,
            error_message: "assessor output failed the agent contract",
          }),
        ],
      })
    );

    const traces = await listDevTraces(DEV_SESSION_ID);

    expect(traces).toHaveLength(2);
    expect(traces[0].outcome).toBe("ok");
    expect(traces[0].wrapper_outcome).toBe("accepted");
    expect(traces[0].transition?.issued_move).toBe("ask_seed");
    // outcome=ok with wrapper_outcome=rejected is a real combination: the model
    // call succeeded, the wrapper refused the output.
    expect(traces[1].outcome).toBe("ok");
    expect(traces[1].wrapper_outcome).toBe("rejected");
    expect(traces[1].parsed).toBeNull();
  });

  it("defaults an absent wrapper_outcome / transition to null (pre-T21 rows)", async () => {
    server.use(
      http.get("*/api/dev/sessions/:sessionId/traces", () =>
        HttpResponse.json({
          traces: [
            {
              id: "8f14e45f-ceea-467a-9c1a-1f4b3f0d5555",
              created_at: "2026-08-03T10:00:00Z",
              interview_session_id: DEV_SESSION_ID,
              agent: "planner",
              prompt_version: "v0001",
              model: "gemini-2.5-pro",
              outcome: "timeout",
              attempts: 3,
              latency_ms: 30000,
              input_tokens: 900,
              output_tokens: 0,
              cost_usd: "0.001000",
              prompt_sha: "cafe1234",
              system_prompt: "…",
              user_payload: "…",
              response_text: "",
            },
          ],
        })
      )
    );

    const [trace] = await listDevTraces(DEV_SESSION_ID);

    expect(trace.wrapper_outcome).toBeNull();
    expect(trace.transition).toBeNull();
    expect(trace.turn_id).toBeNull();
    expect(trace.model_version).toBeNull();
    expect(trace.parsed).toBeNull();
    expect(trace.error_message).toBeNull();
  });

  it("returns an empty list when the traces array is empty", async () => {
    server.use(...devSessionHandlers({ initial: sessionViewFixture() }));
    await expect(listDevTraces(DEV_SESSION_ID)).resolves.toEqual([]);
  });
});

describe("dev session client — failures", () => {
  it("raises ApiError(404) when the flag is off / the session is unknown", async () => {
    server.use(...devSessionStatusHandlers(404));

    const error = await createDevSession({}).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect(isNotFound(error)).toBe(true);
    expect(isPlanInvalid(error)).toBe(false);
  });

  it("raises ApiError(422) with the body when the machine refuses the plan", async () => {
    server.use(
      http.post("*/api/dev/sessions", () =>
        HttpResponse.json({ detail: "PlanInvalid: competencies is empty" }, { status: 422 })
      )
    );

    const error = await createDevSession({}).catch((caught: unknown) => caught);

    expect(isPlanInvalid(error)).toBe(true);
    expect((error as ApiError).body).toEqual({
      detail: "PlanInvalid: competencies is empty",
    });
  });

  it("raises ApiError(409) when the session is not awaiting a candidate turn", async () => {
    server.use(...devSessionStatusHandlers(409));

    const error = await postDevTurn(DEV_SESSION_ID, "…").catch(
      (caught: unknown) => caught
    );

    expect((error as ApiError).status).toBe(409);
    expect(isConflict(error)).toBe(true);
    expect(isNotFound(error)).toBe(false);
  });
});
