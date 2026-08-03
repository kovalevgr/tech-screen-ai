"use client";

// Plan input for the dev console (FR-034-1).
//
// A textarea prefilled with a valid demo PlanSnapshot (state-machine contract
// §7) and a create button. JSON syntax is checked client-side so an obvious
// typo does not cost a round trip; semantic validation stays server-side —
// the machine answers 422 PlanInvalid and the console surfaces that verbatim.

import * as React from "react";

import type { PlanSnapshot } from "@/api/dev-session";
import { DEMO_PLAN_JSON } from "./demo-plan";

export function PlanForm({
  onCreate,
  isPending,
  serverError,
}: {
  onCreate: (plan: PlanSnapshot) => void;
  isPending: boolean;
  serverError: string | null;
}) {
  const [text, setText] = React.useState(DEMO_PLAN_JSON);
  const [parseError, setParseError] = React.useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (error) {
      setParseError(
        `Plan is not valid JSON: ${error instanceof Error ? error.message : String(error)}`
      );
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setParseError("Plan must be a JSON object (state-machine contract §7).");
      return;
    }
    setParseError(null);
    onCreate(parsed as PlanSnapshot);
  }

  return (
    <form onSubmit={handleSubmit} data-testid="plan-form">
      <label
        htmlFor="dev-plan"
        className="block text-body-dense font-semibold text-content-primary"
      >
        PlanSnapshot JSON
      </label>
      <p className="mt-1 max-w-prose text-caption text-content-muted">
        Sent as <code className="font-mono">{"{ plan: … }"}</code> to{" "}
        <code className="font-mono">POST /api/dev/sessions</code>. Prefilled
        with a valid demo plan.
      </p>
      <textarea
        id="dev-plan"
        name="plan"
        rows={18}
        spellCheck={false}
        value={text}
        onChange={(event) => setText(event.target.value)}
        className="mt-2 w-full rounded-md border border-border-default bg-surface-base p-3 font-mono text-caption text-content-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      />
      {parseError ? (
        <p
          role="alert"
          data-testid="plan-parse-error"
          className="mt-2 text-body-dense text-status-danger"
        >
          {parseError}
        </p>
      ) : null}
      {serverError ? (
        <p
          role="alert"
          data-testid="plan-server-error"
          className="mt-2 text-body-dense text-status-danger"
        >
          {serverError}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={isPending}
        className="mt-4 rounded-md border border-border-strong bg-surface-muted px-4 py-2 text-body-dense font-semibold text-content-primary disabled:text-content-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      >
        {isPending ? "Creating session…" : "Create session"}
      </button>
    </form>
  );
}
