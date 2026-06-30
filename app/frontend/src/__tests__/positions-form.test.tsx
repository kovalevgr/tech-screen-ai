// US2/US3 — create, validate, edit, archive. Behaviour assertions against the
// MSW-mocked API. next/navigation is mocked so the page-level router calls are
// observable without a real Next.js runtime.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { renderWithClient } from "@/__tests__/_msw/render";
import { server } from "@/__tests__/_msw/server";
import {
  createValidationErrorHandler,
  getItemNotFoundHandler,
  TEMPLATE_ACTIVE_ID,
} from "@/__tests__/_msw/handlers";

const push = jest.fn();
let routeParams: Record<string, string> = { id: TEMPLATE_ACTIVE_ID };

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: jest.fn(), back: jest.fn() }),
  useParams: () => routeParams,
}));

// Import the pages after the mock is registered.
import NewPositionPage from "@/app/positions/new/page";
import EditPositionPage from "@/app/positions/[id]/page";
import PositionsPage from "@/app/positions/page";

beforeEach(() => {
  push.mockReset();
  routeParams = { id: TEMPLATE_ACTIVE_ID };
});

describe("NewPositionPage — create (US2)", () => {
  it("populates level options and rubric-driven stacks", async () => {
    const user = userEvent.setup();
    renderWithClient(<NewPositionPage />);

    // Stacks come from the rubric.
    expect(await screen.findByText("Backend")).toBeInTheDocument();
    expect(screen.getByText("Frontend")).toBeInTheDocument();

    // The four levels are offered by the Select.
    await user.click(screen.getByRole("combobox", { name: /Рівень/i }));
    for (const lvl of ["Junior", "Middle", "Senior", "Tech Leader"]) {
      expect(
        await screen.findByRole("option", { name: lvl })
      ).toBeInTheDocument();
    }
  });

  it("scopes competencies to the selected stacks", async () => {
    const user = userEvent.setup();
    renderWithClient(<NewPositionPage />);

    await screen.findByText("Backend");
    // No competencies until a stack is chosen.
    expect(screen.queryByText("Python")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Backend" }));
    expect(await screen.findByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Databases")).toBeInTheDocument();
    // Frontend competencies are not offered.
    expect(screen.queryByText("React")).not.toBeInTheDocument();
  });

  it("creates a valid template and returns to the list", async () => {
    const user = userEvent.setup();
    renderWithClient(<NewPositionPage />);

    await screen.findByText("Backend");
    await user.type(
      screen.getByLabelText("Назва"),
      "Платформенний інженер"
    );
    await user.click(screen.getByRole("combobox", { name: /Рівень/i }));
    await user.click(await screen.findByRole("option", { name: "Senior" }));
    await user.click(screen.getByRole("checkbox", { name: "Backend" }));
    await user.click(await screen.findByRole("checkbox", { name: "Python" }));

    await user.click(screen.getByRole("button", { name: "Зберегти" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/positions"));
  });

  it("blocks submit with no competency and shows an inline error", async () => {
    const user = userEvent.setup();
    renderWithClient(<NewPositionPage />);

    await screen.findByText("Backend");
    await user.type(screen.getByLabelText("Назва"), "Роль без компетенцій");
    await user.click(screen.getByRole("combobox", { name: /Рівень/i }));
    await user.click(await screen.findByRole("option", { name: "Junior" }));
    await user.click(screen.getByRole("checkbox", { name: "Backend" }));

    await user.click(screen.getByRole("button", { name: "Зберегти" }));

    expect(
      await screen.findByText("Оберіть хоча б одну компетенцію.")
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("surfaces a server 422 inline and preserves the input", async () => {
    const user = userEvent.setup();
    server.use(createValidationErrorHandler());
    renderWithClient(<NewPositionPage />);

    await screen.findByText("Backend");
    await user.type(screen.getByLabelText("Назва"), "Назва зберігається");
    await user.click(screen.getByRole("combobox", { name: /Рівень/i }));
    await user.click(await screen.findByRole("option", { name: "Middle" }));
    await user.click(screen.getByRole("checkbox", { name: "Backend" }));
    await user.click(await screen.findByRole("checkbox", { name: "Python" }));

    await user.click(screen.getByRole("button", { name: "Зберегти" }));

    // The server's message lands inline; the title input keeps its value.
    expect(
      await screen.findByText(/at least 1 item/i)
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Назва")).toHaveValue("Назва зберігається");
    expect(push).not.toHaveBeenCalled();
  });

  it("disables submit and warns when the rubric cannot load", async () => {
    server.use(getRubricErrorHandler());
    renderWithClient(<NewPositionPage />);

    expect(
      await screen.findByText(
        "Не вдалося завантажити рубрику; створення недоступне."
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Зберегти" })).toBeDisabled();
  });
});

describe("EditPositionPage — edit (US3)", () => {
  it("prefills from the template and saves via PATCH", async () => {
    const user = userEvent.setup();
    renderWithClient(<EditPositionPage />);

    // Prefilled title.
    const titleInput = await screen.findByLabelText("Назва");
    expect(titleInput).toHaveValue("Senior Backend Engineer");
    // Prefilled competency (selected) + its must-have flag.
    expect(await screen.findByText("Python")).toBeInTheDocument();

    await user.clear(titleInput);
    await user.type(titleInput, "Updated Backend Engineer");
    await user.click(screen.getByRole("button", { name: "Зберегти" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/positions"));
  });

  it("shows a not-found state for a missing template", async () => {
    server.use(getItemNotFoundHandler());
    renderWithClient(<EditPositionPage />);
    expect(
      await screen.findByText("Позицію не знайдено.")
    ).toBeInTheDocument();
  });
});

describe("PositionTable — archive (US3)", () => {
  it("confirms then removes the row from the default list", async () => {
    const user = userEvent.setup();
    renderWithClient(<PositionsPage />);

    const row = (await screen.findByText("Senior Backend Engineer")).closest(
      "tr"
    )!;
    await user.click(within(row).getByRole("button", { name: "Архівувати" }));

    // A confirm dialog appears (separate from the row, §13).
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Архівувати позицію?")
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Архівувати" })
    );

    // The row leaves the default (active-only) list.
    await waitFor(() =>
      expect(
        screen.queryByText("Senior Backend Engineer")
      ).not.toBeInTheDocument()
    );
  });

  it("keeps the archived row visible under include-archived", async () => {
    const user = userEvent.setup();
    renderWithClient(<PositionsPage />);

    const row = (await screen.findByText("Senior Backend Engineer")).closest(
      "tr"
    )!;
    await user.click(within(row).getByRole("button", { name: "Архівувати" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Архівувати" })
    );
    await waitFor(() =>
      expect(
        screen.queryByText("Senior Backend Engineer")
      ).not.toBeInTheDocument()
    );

    await user.click(
      screen.getByRole("checkbox", { name: /Показати архівовані/i })
    );
    // The just-archived template is now visible again, marked archived.
    const archivedRow = (
      await screen.findByText("Senior Backend Engineer")
    ).closest("tr")!;
    expect(within(archivedRow).getByText("Архівована")).toBeInTheDocument();
  });
});

// Local helper: a rubric error handler (kept here to avoid widening the shared
// handlers module's public surface for a single test).
function getRubricErrorHandler() {
  return http.get("*/rubric/active", () =>
    HttpResponse.json({ detail: "error" }, { status: 500 })
  );
}
