"use client";

// Session state header for the dev console (FR-034-1).
//
// Every value here is a SessionView field from the contract, labelled with the
// field name so a reviewer can trace what is on screen back to the payload
// (spec 034 SC-3). `coverage` is the machine's own opaque shape, so it is
// summarised by node count and offered raw in a collapsed <details>.

import type { SessionView } from "@/api/dev-session";

function Field({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}) {
  return (
    <div>
      <dt className="font-mono text-small uppercase text-content-muted">
        {label}
      </dt>
      <dd
        data-testid={testId}
        className="mt-1 text-body-dense text-content-primary"
      >
        {value}
      </dd>
    </div>
  );
}

export function SessionHeader({ view }: { view: SessionView }) {
  const coverageNodes = Object.keys(view.coverage);

  return (
    <section
      aria-label="Session state"
      data-testid="session-header"
      className="border border-border-default bg-surface-raised p-4"
    >
      <dl className="flex flex-wrap gap-6">
        <Field label="phase" value={view.phase} testId="header-phase" />
        <Field
          label="awaiting"
          value={view.awaiting ?? "null"}
          testId="header-awaiting"
        />
        <Field
          label="competency_index"
          value={
            view.competency_index === null ? "null" : String(view.competency_index)
          }
          testId="header-competency-index"
        />
        <Field
          label="cost_usd_total"
          value={`$${view.cost_usd_total}`}
          testId="header-cost"
        />
        <Field
          label="coverage"
          value={`${coverageNodes.length} node(s)`}
          testId="header-coverage-count"
        />
        <Field
          label="session_id"
          value={view.session_id}
          testId="header-session-id"
        />
      </dl>

      {view.flagged_for_review ? (
        <p
          data-testid="header-flagged-badge"
          className="mt-4 inline-block rounded-pill border border-status-warning bg-status-warning-subtle px-3 py-1 text-small font-semibold uppercase text-status-warning"
        >
          flagged_for_review
        </p>
      ) : null}

      {coverageNodes.length > 0 ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-caption text-content-secondary">
            coverage JSON
          </summary>
          <pre
            data-testid="header-coverage-json"
            className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-border-subtle bg-surface-muted p-3 font-mono text-small text-content-secondary"
          >
            {JSON.stringify(view.coverage, null, 2)}
          </pre>
        </details>
      ) : null}
    </section>
  );
}
