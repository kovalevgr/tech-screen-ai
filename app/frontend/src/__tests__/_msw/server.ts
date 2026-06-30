// MSW node server for the jest (jsdom) suite. Started/stopped from
// jest.setup.ts; the in-memory store is reset between tests there too.

import { setupServer } from "msw/node";

import { handlers } from "./handlers";

export const server = setupServer(...handlers);
