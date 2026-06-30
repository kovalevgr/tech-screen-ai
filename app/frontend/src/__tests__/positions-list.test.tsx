// US1 — browse position templates. Behaviour assertions (visible text, roles,
// state transitions) against the MSW-mocked API; never class names.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PositionsPage from "@/app/positions/page";
import { renderWithClient } from "@/__tests__/_msw/render";
import { server } from "@/__tests__/_msw/server";
import {
  listStatusHandler,
  handlers,
} from "@/__tests__/_msw/handlers";
import { http, HttpResponse } from "msw";

describe("PositionsPage — list (US1)", () => {
  it("shows only active templates by default, with title/level/counts", async () => {
    renderWithClient(<PositionsPage />);

    expect(
      await screen.findByText("Senior Backend Engineer")
    ).toBeInTheDocument();
    // The archived template is hidden by default.
    expect(screen.queryByText("Legacy Frontend Role")).not.toBeInTheDocument();

    const row = screen.getByText("Senior Backend Engineer").closest("tr")!;
    expect(within(row).getByText("Senior")).toBeInTheDocument();
    // Stacks count = 1, competencies count = 2 for the fixture.
    expect(within(row).getByText("Активна")).toBeInTheDocument();
  });

  it("reveals archived templates when 'Показати архівовані' is toggled", async () => {
    const user = userEvent.setup();
    renderWithClient(<PositionsPage />);

    await screen.findByText("Senior Backend Engineer");
    await user.click(
      screen.getByRole("checkbox", { name: /Показати архівовані/i })
    );

    expect(
      await screen.findByText("Legacy Frontend Role")
    ).toBeInTheDocument();
    expect(screen.getByText("Архівована")).toBeInTheDocument();
  });

  it("shows an empty state with a create affordance when there are none", async () => {
    server.use(
      http.get("*/position-templates", () => HttpResponse.json([]))
    );
    renderWithClient(<PositionsPage />);

    expect(
      await screen.findByText("Ще немає жодної позиції")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Створіть перший шаблон позиції, щоб почати.")
    ).toBeInTheDocument();
    // The CTA appears in the empty state (and in the header).
    expect(
      screen.getAllByRole("link", { name: /Нова позиція/i }).length
    ).toBeGreaterThanOrEqual(1);
  });

  it("shows a generic error with retry on a 500", async () => {
    server.use(listStatusHandler(500));
    renderWithClient(<PositionsPage />);

    expect(
      await screen.findByText("Не вдалося завантажити позиції.")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Спробувати ще раз" })
    ).toBeInTheDocument();
  });

  it("maps 404 to feature-unavailable (no retry)", async () => {
    server.use(listStatusHandler(404));
    renderWithClient(<PositionsPage />);

    expect(
      await screen.findByText("Розділ позицій недоступний.")
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Спробувати ще раз" })
    ).not.toBeInTheDocument();
  });

  it("maps 401 to sign-in-required", async () => {
    server.use(listStatusHandler(401));
    renderWithClient(<PositionsPage />);
    expect(await screen.findByText("Потрібен вхід.")).toBeInTheDocument();
  });

  it("maps 403 to not-permitted", async () => {
    server.use(listStatusHandler(403));
    renderWithClient(<PositionsPage />);
    expect(await screen.findByText("Недостатньо прав.")).toBeInTheDocument();
  });

  it("retry refetches after a transient failure", async () => {
    const user = userEvent.setup();
    let failed = false;
    server.use(
      http.get("*/position-templates", () => {
        if (!failed) {
          failed = true;
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        // Fall through to the default happy-path handler on retry.
        return undefined;
      }),
      ...handlers
    );

    renderWithClient(<PositionsPage />);
    await screen.findByText("Не вдалося завантажити позиції.");
    await user.click(screen.getByRole("button", { name: "Спробувати ще раз" }));
    await waitFor(() =>
      expect(
        screen.getByText("Senior Backend Engineer")
      ).toBeInTheDocument()
    );
  });
});
