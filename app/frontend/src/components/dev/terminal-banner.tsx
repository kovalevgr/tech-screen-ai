"use client";

// Terminal-state banner (FR-034-5).
//
// COMPLETED and ABORTED are rendered honestly and differently: COMPLETED
// points at the scripted closing that is already the last transcript entry;
// ABORTED names its `abort_reason` (candidate_timeout | cost_ceiling |
// operator_abort | fatal_agent_error — state-machine contract §2).

import type { DevPhase } from "@/api/dev-session";

export function TerminalBanner({
  phase,
  abortReason,
}: {
  phase: DevPhase;
  abortReason: string | null;
}) {
  if (phase === "COMPLETED") {
    return (
      <p
        role="status"
        data-testid="terminal-banner"
        className="border border-status-success bg-status-success-subtle p-3 text-body-dense text-status-success"
      >
        Session COMPLETED — the scripted closing is the last message in the
        thread. No further turns are accepted.
      </p>
    );
  }

  if (phase === "ABORTED") {
    return (
      <p
        role="status"
        data-testid="terminal-banner"
        className="border border-status-danger bg-status-danger-subtle p-3 text-body-dense text-status-danger"
      >
        Session ABORTED — abort_reason:{" "}
        <span className="font-mono font-semibold">
          {abortReason ?? "unknown"}
        </span>
      </p>
    );
  }

  return null;
}
