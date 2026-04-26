// Flat ESLint config for the TechScreen frontend.
// Wraps the legacy `next/core-web-vitals` shareable config and the T01 TypeScript
// + Prettier baseline via FlatCompat (eslint-config-next is still .eslintrc-style
// upstream as of v15).
import { FlatCompat } from "@eslint/eslintrc";
import js from "@eslint/js";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const compat = new FlatCompat({
  baseDirectory: __dirname,
  recommendedConfig: js.configs.recommended,
});

const config = [
  {
    ignores: ["node_modules", ".next", "dist", "out", "coverage", "next-env.d.ts"],
  },
  ...compat.extends(
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "next/core-web-vitals",
    "prettier",
  ),
];

export default config;
