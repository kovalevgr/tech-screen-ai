import type { Config } from "jest";
import nextJest from "next/jest";

const createJestConfig = nextJest({ dir: "./" });

// MSW v2 needs Node's fetch/Request/Response/stream primitives, which the
// stock jsdom environment strips. `jest-fixed-jsdom` is a drop-in jsdom that
// keeps them.
const baseConfig: Config = {
  setupFilesAfterEnv: ["./jest.setup.ts"],
  testEnvironment: "jest-fixed-jsdom",
  // MSW's `msw/node` server picks its request interceptor from package
  // `exports` conditions; the empty condition makes the resolver fall through
  // to the node build so the fetch interceptor binds (the documented MSW v2 +
  // jest-fixed-jsdom recipe).
  testEnvironmentOptions: {
    customExportConditions: [""],
  },
  testMatch: ["<rootDir>/src/__tests__/**/*.{test,spec}.{ts,tsx}"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
};

// next/jest injects its own `transformIgnorePatterns` (which would ignore the
// ESM-only packages MSW pulls in, e.g. `rettime`). We override them *after*
// next/jest has produced the resolved config so Babel transforms those
// packages instead of choking on their ESM `import` syntax.
const MSW_ESM_PACKAGES = [
  "msw",
  "@mswjs\\+",
  "@bundled-es-modules\\+",
  "@open-draft\\+",
  "rettime",
  "until-async",
  "strict-event-emitter",
  "outvariant",
  "headers-polyfill",
  "is-node-process",
].join("|");

export default async function jestConfig() {
  const resolved = await createJestConfig(baseConfig)();
  return {
    ...resolved,
    transformIgnorePatterns: [
      `/node_modules/.pnpm/(?!(${MSW_ESM_PACKAGES})@?)`,
      "^.+\\.module\\.(css|sass|scss)$",
    ],
  };
}
