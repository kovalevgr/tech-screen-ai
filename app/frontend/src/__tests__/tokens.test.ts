/** @jest-environment node */

// Token-drift Jest test (FR-006). Mirrors T02's test_openapi_regeneration.py
// pattern: regenerate the artefacts in memory from docs/design/tokens/*.md and
// assert byte-equality against the committed files. On failure, surface the
// first ~40 lines of a unified-diff head so the offending role is immediately
// identifiable in CI output.
//
// `@jest-environment node` overrides the project-wide jsdom default
// (jest.config.ts) — this test is pure file I/O, no DOM access.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { generate } from "../../scripts/generate-tokens";

const REPO_ROOT = resolve(__dirname, "..", "..", "..", "..");
const TOKENS_TS_PATH = resolve(REPO_ROOT, "app/frontend/src/design/tokens.ts");
const GLOBALS_CSS_PATH = resolve(REPO_ROOT, "app/frontend/src/app/globals.css");

function diffHead(committed: string, regenerated: string, label: string, max = 40): string {
  const c = committed.split("\n");
  const r = regenerated.split("\n");
  const out: string[] = [`--- ${label} (committed)`, `+++ ${label} (regenerated)`];
  const len = Math.max(c.length, r.length);
  for (let i = 0; i < len && out.length < max + 2; i += 1) {
    const cl = c[i] ?? "";
    const rl = r[i] ?? "";
    if (cl === rl) continue;
    out.push(`-${cl}`);
    out.push(`+${rl}`);
  }
  return out.slice(0, max + 2).join("\n");
}

describe("tokens artefacts match the generator output", () => {
  test("tokens.ts is byte-equal to the regenerated output", () => {
    const { tokensTs } = generate();
    const committed = readFileSync(TOKENS_TS_PATH, "utf8");
    if (committed !== tokensTs) {
      throw new Error(
        `tokens.ts drift detected:\n${diffHead(committed, tokensTs, "src/design/tokens.ts")}`,
      );
    }
  });

  test("globals.css TOKENS region is byte-equal to the regenerated output", () => {
    const { globalsCss } = generate();
    const committed = readFileSync(GLOBALS_CSS_PATH, "utf8");
    if (committed !== globalsCss) {
      throw new Error(
        `globals.css drift detected:\n${diffHead(committed, globalsCss, "src/app/globals.css")}`,
      );
    }
  });
});
