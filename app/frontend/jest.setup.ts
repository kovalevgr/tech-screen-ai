import "@testing-library/jest-dom";

// The `jest-fixed-jsdom` environment (see jest.config.ts) keeps Node's
// fetch / Request / Response / stream primitives that MSW v2 needs, so no
// manual fetch polyfill is required here.

// jsdom lacks a few DOM APIs the Radix primitives (Select) call. Stub them so
// rendering does not throw under jest.
const w = globalThis as unknown as Record<string, unknown>;
if (!w.ResizeObserver) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  w.ResizeObserver = ResizeObserverStub;
}
if (!w.DOMRect) {
  // Minimal DOMRect used by Radix positioning code paths.
  class DOMRectStub {
    constructor(
      public x = 0,
      public y = 0,
      public width = 0,
      public height = 0
    ) {}
    top = 0;
    right = 0;
    bottom = 0;
    left = 0;
    toJSON() {
      return {};
    }
  }
  w.DOMRect = DOMRectStub;
}
if (typeof Element !== "undefined") {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function scrollIntoView() {};
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = function hasPointerCapture() {
      return false;
    };
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = function setPointerCapture() {};
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture =
      function releasePointerCapture() {};
  }
}

// Stable API base for tests; handlers match any origin via a `*` wildcard.
process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";

// eslint-disable-next-line import/first
import { server } from "@/__tests__/_msw/server";
// eslint-disable-next-line import/first
import { resetStore } from "@/__tests__/_msw/handlers";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  resetStore();
});
afterAll(() => server.close());
