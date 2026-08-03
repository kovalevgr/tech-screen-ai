// T22 — polling behaviour of the dev session view (FR-034-4).
//
// The console keeps a light interval poll while the session is live and stops
// it on the terminal phases. Both halves are asserted: the pure interval
// decision, and the actual refetch cadence of the hook under fake timers.

import * as React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import {
  DEV_SESSION_POLL_MS,
  sessionPollInterval,
  useDevSession,
} from "@/api/dev-session";
import {
  DEV_SESSION_ID,
  sessionViewFixture,
} from "@/__tests__/_msw/dev-session-handlers";
import { server } from "@/__tests__/_msw/server";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("sessionPollInterval", () => {
  it("polls while the session is live", () => {
    expect(sessionPollInterval(sessionViewFixture({ phase: "INTRO" }))).toBe(
      DEV_SESSION_POLL_MS
    );
    expect(
      sessionPollInterval(
        sessionViewFixture({ phase: "TECH", awaiting: "interviewer" })
      )
    ).toBe(DEV_SESSION_POLL_MS);
    expect(sessionPollInterval(sessionViewFixture({ phase: "QA" }))).toBe(
      DEV_SESSION_POLL_MS
    );
  });

  it("stops on the terminal phases and before the first view arrives", () => {
    expect(sessionPollInterval(undefined)).toBe(false);
    expect(
      sessionPollInterval(sessionViewFixture({ phase: "COMPLETED" }))
    ).toBe(false);
    expect(
      sessionPollInterval(
        sessionViewFixture({ phase: "ABORTED", abort_reason: "operator_abort" })
      )
    ).toBe(false);
  });
});

describe("useDevSession polling", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("refetches the view on the interval while the session is live", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/dev/sessions/:sessionId", () => {
        calls += 1;
        return HttpResponse.json(sessionViewFixture());
      })
    );

    const { result } = renderHook(() => useDevSession(DEV_SESSION_ID), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(calls).toBe(1);

    await act(async () => {
      jest.advanceTimersByTime(DEV_SESSION_POLL_MS);
    });
    await waitFor(() => expect(calls).toBe(2));
  });

  it("issues no further requests once the phase is terminal", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/dev/sessions/:sessionId", () => {
        calls += 1;
        return HttpResponse.json(sessionViewFixture({ phase: "COMPLETED" }));
      })
    );

    const { result } = renderHook(() => useDevSession(DEV_SESSION_ID), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(calls).toBe(1);

    await act(async () => {
      jest.advanceTimersByTime(DEV_SESSION_POLL_MS * 3);
    });
    expect(calls).toBe(1);
  });
});
