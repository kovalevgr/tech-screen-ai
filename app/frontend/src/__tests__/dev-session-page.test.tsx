// T22 — /dev/session console (FR-034-1, -2, -4, -5, -6).
//
// Behaviour assertions against the MSW-mocked dev session API: what the
// operator sees, when the input is allowed, what the trace panel shows, and
// how the terminal / flag-off states render. Never class names.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DevSessionPage from "@/app/dev/session/page";
import {
  DEV_SESSION_ID,
  devSessionHandlers,
  devSessionStatusHandlers,
  sessionViewFixture,
  traceRowFixture,
} from "@/__tests__/_msw/dev-session-handlers";
import { renderWithClient } from "@/__tests__/_msw/render";
import { server } from "@/__tests__/_msw/server";

async function createSession(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Create session" }));
  return screen.findByTestId("session-header");
}

describe("DevSessionPage — plan input", () => {
  it("warns about the DEV ONLY status and prefills a valid demo plan", () => {
    renderWithClient(<DevSessionPage />);

    expect(screen.getByTestId("dev-only-banner")).toHaveTextContent(/dev only/i);
    expect(screen.getByTestId("dev-only-banner")).toHaveTextContent(
      "enable_live_orchestrator"
    );

    const textarea = screen.getByLabelText("PlanSnapshot JSON");
    expect(JSON.parse((textarea as HTMLTextAreaElement).value)).toMatchObject({
      plan_version: 1,
    });
  });

  it("refuses to send a plan that is not JSON", async () => {
    const user = userEvent.setup();
    renderWithClient(<DevSessionPage />);

    const textarea = screen.getByLabelText("PlanSnapshot JSON");
    await user.clear(textarea);
    await user.type(textarea, "not-json");
    await user.click(screen.getByRole("button", { name: "Create session" }));

    expect(await screen.findByTestId("plan-parse-error")).toHaveTextContent(
      /not valid JSON/i
    );
    expect(screen.queryByTestId("session-header")).not.toBeInTheDocument();
  });

  it("surfaces a 422 PlanInvalid from the machine", async () => {
    const user = userEvent.setup();
    server.use(...devSessionStatusHandlers(422));
    renderWithClient(<DevSessionPage />);

    await user.click(screen.getByRole("button", { name: "Create session" }));

    expect(await screen.findByTestId("plan-server-error")).toHaveTextContent(
      /422 PlanInvalid/
    );
  });
});

describe("DevSessionPage — session view", () => {
  it("renders the state header and the transcript after create", async () => {
    const user = userEvent.setup();
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture({
          flagged_for_review: true,
          competency_index: 1,
        }),
      })
    );
    renderWithClient(<DevSessionPage />);

    const header = await createSession(user);

    expect(within(header).getByTestId("header-phase")).toHaveTextContent("TECH");
    expect(within(header).getByTestId("header-awaiting")).toHaveTextContent(
      "candidate"
    );
    expect(
      within(header).getByTestId("header-competency-index")
    ).toHaveTextContent("1");
    expect(within(header).getByTestId("header-cost")).toHaveTextContent(
      "$0.041200"
    );
    expect(within(header).getByTestId("header-session-id")).toHaveTextContent(
      DEV_SESSION_ID
    );
    expect(
      within(header).getByTestId("header-flagged-badge")
    ).toBeInTheDocument();

    const messages = screen.getAllByTestId("chat-message");
    expect(messages).toHaveLength(2);
    expect(messages[0]).toHaveAttribute("data-role", "system");
    expect(messages[1]).toHaveTextContent("event loop");
    expect(screen.getByTestId("poll-status")).toHaveTextContent(
      "Polling every 4s."
    );
  });

  it("hides the flag badge when the session is not flagged", async () => {
    const user = userEvent.setup();
    server.use(...devSessionHandlers({ initial: sessionViewFixture() }));
    renderWithClient(<DevSessionPage />);

    await createSession(user);

    expect(
      screen.queryByTestId("header-flagged-badge")
    ).not.toBeInTheDocument();
  });
});

describe("DevSessionPage — turn gating (awaiting)", () => {
  it("enables the input only while awaiting == candidate", async () => {
    const user = userEvent.setup();
    server.use(...devSessionHandlers({ initial: sessionViewFixture() }));
    renderWithClient(<DevSessionPage />);

    await createSession(user);

    expect(screen.getByLabelText("Candidate turn")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send turn" })).toBeEnabled();
    expect(screen.getByTestId("turn-hint")).toHaveTextContent(
      "awaiting a candidate turn"
    );
  });

  it("disables the input while awaiting == interviewer", async () => {
    const user = userEvent.setup();
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture({ awaiting: "interviewer" }),
      })
    );
    renderWithClient(<DevSessionPage />);

    await createSession(user);

    expect(screen.getByLabelText("Candidate turn")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send turn" })).toBeDisabled();
    expect(screen.getByTestId("turn-hint")).toHaveTextContent(
      "Waiting for the interviewer"
    );
  });

  it("posts the typed turn and renders the machine's answer", async () => {
    const user = userEvent.setup();
    let posted = "";
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture(),
        onTurn: (text, current) => {
          posted = text;
          return {
            utterance: "А що станеться при блокуючому виклику?",
            session: {
              ...current,
              awaiting: "candidate",
              cost_usd_total: "0.052300",
              transcript: [
                ...current.transcript,
                { role: "candidate", text, turn_id: null },
                {
                  role: "interviewer",
                  text: "А що станеться при блокуючому виклику?",
                  turn_id: null,
                },
              ],
            },
          };
        },
      })
    );
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    await user.type(screen.getByLabelText("Candidate turn"), "event loop крутить корутини");
    await user.click(screen.getByRole("button", { name: "Send turn" }));

    await waitFor(() =>
      expect(screen.getAllByTestId("chat-message")).toHaveLength(4)
    );
    expect(posted).toBe("event loop крутить корутини");
    expect(screen.getByTestId("last-utterance")).toHaveTextContent(
      "А що станеться при блокуючому виклику?"
    );
    expect(screen.getByTestId("header-cost")).toHaveTextContent("$0.052300");
    // The composer clears after a successful turn.
    expect(screen.getByLabelText("Candidate turn")).toHaveValue("");
  });

  it("reports a 409 from a turn that the machine did not expect", async () => {
    const user = userEvent.setup();
    server.use(...devSessionHandlers({ initial: sessionViewFixture() }));
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    await user.type(screen.getByLabelText("Candidate turn"), "пізня відповідь");
    server.use(...devSessionStatusHandlers(409));
    await user.click(screen.getByRole("button", { name: "Send turn" }));

    expect(await screen.findByTestId("turn-error")).toHaveTextContent(
      "409 — the session is terminal or not awaiting a candidate turn."
    );
    // The text stays put so the operator can retry.
    expect(screen.getByLabelText("Candidate turn")).toHaveValue(
      "пізня відповідь"
    );
  });
});

describe("DevSessionPage — trace side panel", () => {
  it("is collapsed by default and expands to raw pretty-printed rows", async () => {
    const user = userEvent.setup();
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
          }),
        ],
      })
    );
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    const toggle = screen.getByTestId("trace-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("trace-row")).not.toBeInTheDocument();

    await user.click(toggle);

    const rows = await screen.findAllByTestId("trace-row");
    expect(rows).toHaveLength(2);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    // outcome (model call) and wrapper_outcome (agent wrapper) are distinct.
    expect(within(rows[0]).getByTestId("trace-outcome")).toHaveTextContent(
      "outcome: ok"
    );
    expect(
      within(rows[0]).getByTestId("trace-wrapper-outcome")
    ).toHaveTextContent("wrapper_outcome: accepted");
    expect(within(rows[1]).getByTestId("trace-outcome")).toHaveTextContent(
      "outcome: ok"
    );
    expect(
      within(rows[1]).getByTestId("trace-wrapper-outcome")
    ).toHaveTextContent("wrapper_outcome: rejected");

    // Raw JSON, pretty-printed, nothing filtered out.
    const json = within(rows[0]).getByTestId("trace-json");
    expect(json).toHaveTextContent('"prompt_sha": "b4c1d2e3f4a5b6c7"');
    expect(json).toHaveTextContent('"state_after_sha": "bbb222"');
    expect(json.textContent).toContain("\n");

    await user.click(toggle);
    expect(screen.queryByTestId("trace-row")).not.toBeInTheDocument();
  });

  it("labels a null wrapper_outcome instead of hiding it", async () => {
    const user = userEvent.setup();
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture(),
        traces: [traceRowFixture({ wrapper_outcome: null, outcome: "timeout" })],
      })
    );
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    await user.click(screen.getByTestId("trace-toggle"));

    const row = await screen.findByTestId("trace-row");
    expect(within(row).getByTestId("trace-outcome")).toHaveTextContent(
      "outcome: timeout"
    );
    expect(within(row).getByTestId("trace-wrapper-outcome")).toHaveTextContent(
      "wrapper_outcome: null"
    );
  });

  it("shows an empty state when the session has no traces yet", async () => {
    const user = userEvent.setup();
    server.use(...devSessionHandlers({ initial: sessionViewFixture() }));
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    await user.click(screen.getByTestId("trace-toggle"));

    expect(await screen.findByTestId("trace-empty")).toBeInTheDocument();
  });
});

describe("DevSessionPage — terminal and unavailable states", () => {
  it("renders ABORTED with its reason and stops accepting turns", async () => {
    const user = userEvent.setup();
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture({
          phase: "ABORTED",
          abort_reason: "candidate_timeout",
          awaiting: null,
        }),
      })
    );
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    const banner = screen.getByTestId("terminal-banner");
    expect(banner).toHaveTextContent("Session ABORTED");
    expect(banner).toHaveTextContent("candidate_timeout");
    expect(screen.getByLabelText("Candidate turn")).toBeDisabled();
    expect(screen.getByTestId("poll-status")).toHaveTextContent(
      "Polling stopped — terminal phase."
    );
  });

  it("renders COMPLETED with the closing message and a null utterance", async () => {
    const user = userEvent.setup();
    server.use(
      ...devSessionHandlers({
        initial: sessionViewFixture(),
        onTurn: (text, current) => ({
          utterance: null,
          session: {
            ...current,
            phase: "COMPLETED",
            awaiting: null,
            transcript: [
              ...current.transcript,
              { role: "candidate", text, turn_id: null },
              {
                role: "system",
                text: "Дякуємо за розмову. Ми повернемось із результатом.",
                turn_id: null,
              },
            ],
          },
        }),
      })
    );
    renderWithClient(<DevSessionPage />);
    await createSession(user);

    await user.type(screen.getByLabelText("Candidate turn"), "готовий завершити");
    await user.click(screen.getByRole("button", { name: "Send turn" }));

    expect(await screen.findByTestId("terminal-banner")).toHaveTextContent(
      "Session COMPLETED"
    );
    expect(
      screen.getByText("Дякуємо за розмову. Ми повернемось із результатом.")
    ).toBeInTheDocument();
    expect(screen.getByTestId("last-utterance")).toHaveTextContent(
      "null — the session ended on this turn"
    );
    expect(screen.getByLabelText("Candidate turn")).toBeDisabled();
  });

  it("explains a 404 as the disabled dev API instead of crashing", async () => {
    const user = userEvent.setup();
    server.use(...devSessionStatusHandlers(404));
    renderWithClient(<DevSessionPage />);

    await user.click(screen.getByRole("button", { name: "Create session" }));

    const notice = await screen.findByTestId("api-disabled-notice");
    expect(notice).toHaveTextContent("enable_live_orchestrator");
    expect(notice).toHaveTextContent("404");
    expect(screen.queryByTestId("plan-form")).not.toBeInTheDocument();
  });
});
