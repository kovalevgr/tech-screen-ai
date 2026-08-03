"use client";

// /dev/session — internal orchestrator console (T22, spec 034 FR-034-1).
// Dev-only surface: not the candidate interview UI and not on the Chat-iX
// design baseline (implementation plan T22 excludes it from the design gates).
// The route is only useful while the `enable_live_orchestrator` flag is on;
// with the flag off the API answers 404 and the console says so.

import { DevSessionConsole } from "@/components/dev/dev-session-console";

export default function DevSessionPage() {
  return <DevSessionConsole />;
}
