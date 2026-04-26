// Admin-shell smoke test (FR-011, US4).
//
// Mounts <Shell> through the next/jest pipeline and JSDOM. Per the
// spec Clarifications "rendering pipeline" Q&A, <Shell> IS the chrome
// layer — app/layout.tsx is a one-line <body><Shell>{children}</Shell>
// wrapper around it, so mounting <Shell> here exercises the full
// chrome composition (TopBar + Sidebar + 3x shadcn Button) through
// React's reconciliation pipeline.
//
// Three assertions, mapping to FR-011(a)/(b)/(c):
//   1. Wordmark "N-iX TechScreen" rendered.
//   2. Three nav buttons (Dashboard / Sessions / Settings) rendered.
//   3. Keyboard tab advances focus across the buttons; the focused
//      element carries the focus-ring utility class (the ring fill
//      resolves through `--ring` → `--focus-ring` → `--brand-primary`).

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Shell } from "@/components/shell/shell";

describe("admin shell smoke test", () => {
  it("renders the wordmark, three nav buttons, and routes focus through them", async () => {
    render(
      <Shell>
        <p>content</p>
      </Shell>,
    );

    // (1) Wordmark — FR-011(a).
    expect(screen.getByText(/N-iX TechScreen/i)).toBeInTheDocument();

    // (2) Three nav buttons — FR-011(b).
    const navButtons = screen.getAllByRole("button", {
      name: /Dashboard|Sessions|Settings/i,
    });
    expect(navButtons.length).toBeGreaterThanOrEqual(3);

    const labels = navButtons.map((btn) => btn.textContent?.trim());
    expect(labels).toEqual(expect.arrayContaining(["Dashboard", "Sessions", "Settings"]));

    // (3) Keyboard tab advances focus across the buttons in order;
    //     the focused button carries the focus-ring utility, so the
    //     visible ring renders via `--ring`. — FR-011(c).
    const user = userEvent.setup();
    await user.tab();
    expect(document.activeElement).toBe(navButtons[0]);
    expect(navButtons[0].className).toContain("focus-visible:ring-ring");

    await user.tab();
    expect(document.activeElement).toBe(navButtons[1]);

    await user.tab();
    expect(document.activeElement).toBe(navButtons[2]);
  });
});
