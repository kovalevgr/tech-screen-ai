// DEV ONLY banner for the /dev/session console (FR-034-1, spec 034
// Clarification 2). This page is an internal orchestrator console: it is NOT
// the candidate surface and NOT on the Chat-iX design baseline (implementation
// plan T22 excludes it from the design gates), so the banner states that
// plainly at the top of every render.

export function DevOnlyBanner() {
  return (
    <div
      role="note"
      data-testid="dev-only-banner"
      className="border border-status-warning bg-status-warning-subtle p-3 text-body-dense text-status-warning"
    >
      <span className="font-semibold uppercase">Dev only</span> — internal
      orchestrator console. Not the candidate surface, not on the design
      baseline. Requires the{" "}
      <code className="font-mono">enable_live_orchestrator</code> feature flag.
    </div>
  );
}
