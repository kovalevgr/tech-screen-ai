import type { Config } from "tailwindcss";
import { tokens } from "./src/design/tokens";

// `tokens` is `as const` (readonly literal types) for compile-time narrowing in
// app code; Tailwind's Config types expect mutable counterparts, so we widen
// at this single boundary via a structural cast.
const writable = <T>(v: T): T => v as T;

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  // intentionally no-op at MVP: visual-discipline pre-commit blocks dark-mode Tailwind variants (FR-010); future dark mode is a deliberate project (design principle §6), not a flag.
  darkMode: "class",
  theme: {
    // OVERRIDE — per docs/design/tokens/spacing.md Export note, the default Tailwind
    // spacing scale is replaced (no `extend`) so stray utilities like `w-7` cannot leak in.
    spacing: writable<Record<string, string>>({ ...tokens.space }),
    extend: {
      colors: writable({ ...tokens.colors }),
      fontSize: writable({ ...tokens.fontSize }) as unknown as Record<
        string,
        string | [string, { lineHeight: string }]
      >,
      fontFamily: writable({ ...tokens.fontFamily }),
      borderRadius: writable({ ...tokens.borderRadius }),
      transitionDuration: writable({ ...tokens.transitionDuration }),
    },
  },
  plugins: [],
};

export default config;
