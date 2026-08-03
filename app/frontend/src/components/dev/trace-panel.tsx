"use client";

// Turn-trace side panel (FR-034-2).
//
// Collapsed by default (the parent owns the toggle and only fetches traces
// while it is open). Each row is one durable turn_trace record — the audit
// row a reviewer will read years later — rendered as a summary line plus the
// full raw JSON, pretty-printed, with nothing filtered out.
//
// The two outcome fields are deliberately shown as two separate chips:
// `outcome` is the MODEL call result and `wrapper_outcome` is whether the
// agent wrapper accepted that output. A row can be `outcome=ok` +
// `wrapper_outcome=rejected` (turn-trace schema, `outcome` description); the
// panel must never let those collapse into one "status".

import type { TurnTraceRow, WrapperOutcome } from "@/api/dev-session";

const CHIP_BASE =
  "rounded-pill border px-2 py-1 font-mono text-small font-semibold";
const CHIP_OK = "border-status-success bg-status-success-subtle text-status-success";
const CHIP_WARN = "border-status-warning bg-status-warning-subtle text-status-warning";
const CHIP_BAD = "border-status-danger bg-status-danger-subtle text-status-danger";
const CHIP_NEUTRAL =
  "border-status-neutral bg-status-neutral-subtle text-status-neutral";

function wrapperChipClass(value: WrapperOutcome): string {
  if (value === "accepted") return CHIP_OK;
  if (value === "contract_miss_retried") return CHIP_WARN;
  if (value === "rejected") return CHIP_BAD;
  return CHIP_NEUTRAL;
}

function TraceRow({ trace }: { trace: TurnTraceRow }) {
  return (
    <li
      data-testid="trace-row"
      className="border border-border-subtle bg-surface-base p-3"
    >
      <details>
        <summary className="cursor-pointer">
          <span className="font-mono text-body-dense font-semibold text-content-primary">
            {trace.agent}
          </span>{" "}
          <span
            data-testid="trace-outcome"
            className={`${CHIP_BASE} ${trace.outcome === "ok" ? CHIP_OK : CHIP_BAD}`}
          >
            outcome: {trace.outcome}
          </span>{" "}
          <span
            data-testid="trace-wrapper-outcome"
            className={`${CHIP_BASE} ${wrapperChipClass(trace.wrapper_outcome)}`}
          >
            wrapper_outcome: {trace.wrapper_outcome ?? "null"}
          </span>
          <span className="ml-2 font-mono text-small text-content-muted">
            {trace.latency_ms} ms · ${trace.cost_usd} · attempts{" "}
            {trace.attempts}
          </span>
        </summary>
        <pre
          data-testid="trace-json"
          className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-border-subtle bg-surface-muted p-3 font-mono text-small text-content-secondary"
        >
          {JSON.stringify(trace, null, 2)}
        </pre>
      </details>
    </li>
  );
}

export function TracePanel({
  open,
  traces,
  isLoading,
  error,
}: {
  open: boolean;
  traces: TurnTraceRow[] | undefined;
  isLoading: boolean;
  error: string | null;
}) {
  return (
    <aside
      id="trace-panel"
      hidden={!open}
      aria-label="Turn traces"
      className="w-full border border-border-default bg-surface-raised p-4 lg:w-2/5"
    >
      {open ? (
        <>
          <h2 className="text-body font-semibold text-content-primary">
            Turn traces
          </h2>
          <p className="mt-1 text-caption text-content-muted">
            GET /api/dev/sessions/{"{id}"}/traces — oldest first, raw rows.
          </p>
          {error ? (
            <p
              role="alert"
              data-testid="trace-error"
              className="mt-3 text-body-dense text-status-danger"
            >
              {error}
            </p>
          ) : null}
          {isLoading ? (
            <p data-testid="trace-loading" className="mt-3 text-body-dense text-content-muted">
              Loading traces…
            </p>
          ) : null}
          {!isLoading && !error && (traces?.length ?? 0) === 0 ? (
            <p data-testid="trace-empty" className="mt-3 text-body-dense text-content-muted">
              No traces yet.
            </p>
          ) : null}
          {traces && traces.length > 0 ? (
            <ol className="mt-3 flex flex-col gap-2">
              {traces.map((trace) => (
                <TraceRow key={trace.id} trace={trace} />
              ))}
            </ol>
          ) : null}
        </>
      ) : null}
    </aside>
  );
}
