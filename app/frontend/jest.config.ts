import nextJest from "next/jest";

const createJestConfig = nextJest({ dir: "./" });

export default createJestConfig({
  setupFilesAfterEnv: ["./jest.setup.ts"],
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/__tests__/**/*.{test,spec}.{ts,tsx}"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
});
