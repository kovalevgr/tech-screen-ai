// 404 screen for the dev session API (FR-034-5).
//
// The contract returns 404 for two reasons: the `enable_live_orchestrator`
// flag is off (routes answer 404-as-if-absent, §9 dark launch) or the session
// id is unknown. The console cannot tell them apart, so it names both instead
// of guessing — and never crashes on the 404.

export function ApiDisabledNotice({ detail }: { detail?: string }) {
  return (
    <section
      data-testid="api-disabled-notice"
      className="border border-border-default bg-surface-muted p-6"
    >
      <h2 className="text-title font-semibold text-content-primary">
        Dev session API unavailable (404)
      </h2>
      <p className="mt-3 max-w-prose text-body-dense text-content-secondary">
        The dev API is disabled (
        <code className="font-mono">enable_live_orchestrator</code> is off — the
        routes answer 404 as if absent) or the session id is unknown.
      </p>
      <p className="mt-3 max-w-prose text-body-dense text-content-secondary">
        Enable the flag for this environment, then reload and create a new
        session.
      </p>
      {detail ? (
        <p className="mt-3 font-mono text-caption text-content-muted">
          {detail}
        </p>
      ) : null}
    </section>
  );
}
