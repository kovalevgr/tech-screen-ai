"use client";

// Dev conversation console (T22, spec 034).
//
// Drives a whole mock interview against the dev session API: plan in →
// session created → candidate turns → interviewer replies → terminal state,
// with the raw turn traces available in a side panel. It is the imperative
// shell's UI counterpart: the state machine decides everything (phase,
// turn-taking, abort), this page only renders what the SessionView reports and
// posts what the operator types.
//
// Contract: specs/034-t22-dev-session-ui/contract-snapshot.yaml.

import * as React from "react";

import {
  DEV_SESSION_POLL_MS,
  isConflict,
  isNotFound,
  isPlanInvalid,
  isTerminalPhase,
  useCreateDevSession,
  useDevSession,
  useDevTraces,
  usePostDevTurn,
  type PlanSnapshot,
} from "@/api/dev-session";
import { ApiDisabledNotice } from "./api-disabled-notice";
import { ChatThread } from "./chat-thread";
import { DevOnlyBanner } from "./dev-only-banner";
import { PlanForm } from "./plan-form";
import { SessionHeader } from "./session-header";
import { TerminalBanner } from "./terminal-banner";
import { TracePanel } from "./trace-panel";
import { TurnComposer } from "./turn-composer";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed.";
}

// 404 is rendered as its own screen, so it is filtered out here.
function createErrorMessage(error: unknown): string | null {
  if (!error || isNotFound(error)) return null;
  if (isPlanInvalid(error)) {
    return "422 PlanInvalid — the state machine refused this plan (state-machine contract §7).";
  }
  return messageOf(error);
}

function turnErrorMessage(error: unknown): string | null {
  if (!error || isNotFound(error)) return null;
  if (isConflict(error)) {
    return "409 — the session is terminal or not awaiting a candidate turn.";
  }
  return messageOf(error);
}

export function DevSessionConsole() {
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [tracesOpen, setTracesOpen] = React.useState(false);
  // `undefined` = no turn posted yet; `null` = the contract's null utterance.
  const [lastUtterance, setLastUtterance] = React.useState<
    string | null | undefined
  >(undefined);

  const create = useCreateDevSession();
  const sessionQuery = useDevSession(sessionId);
  const view = sessionQuery.data;
  const terminal = view ? isTerminalPhase(view.phase) : false;
  const traceQuery = useDevTraces(sessionId, {
    enabled: tracesOpen,
    poll: tracesOpen && !terminal,
  });
  const postTurn = usePostDevTurn(sessionId);

  const notFound =
    isNotFound(create.error) ||
    isNotFound(sessionQuery.error) ||
    isNotFound(postTurn.error);

  function handleCreate(plan: PlanSnapshot) {
    setLastUtterance(undefined);
    create.mutate(plan, {
      onSuccess: (created) => setSessionId(created.session_id),
    });
  }

  async function handleSend(text: string) {
    const result = await postTurn.mutateAsync(text);
    setLastUtterance(result.utterance);
    return result;
  }

  return (
    <div className="mx-auto max-w-screen-xl p-6">
      <DevOnlyBanner />

      <h1 className="mt-6 text-headline font-semibold text-content-primary">
        Dev session console
      </h1>
      <p className="mt-1 max-w-prose text-body-dense text-content-secondary">
        Drives the orchestrator through the dev session API. Synthetic plans and
        answers only.
      </p>

      {notFound ? (
        <div className="mt-6">
          <ApiDisabledNotice
            detail={messageOf(
              create.error ?? sessionQuery.error ?? postTurn.error
            )}
          />
        </div>
      ) : view === undefined ? (
        <div className="mt-6">
          <PlanForm
            onCreate={handleCreate}
            isPending={create.isPending}
            serverError={createErrorMessage(create.error)}
          />
        </div>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          <SessionHeader view={view} />
          <TerminalBanner
            phase={view.phase}
            abortReason={view.abort_reason}
          />

          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              data-testid="trace-toggle"
              aria-expanded={tracesOpen}
              aria-controls="trace-panel"
              onClick={() => setTracesOpen((open) => !open)}
              className="rounded-md border border-border-strong bg-surface-muted px-4 py-2 text-body-dense font-semibold text-content-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              {tracesOpen ? "Hide turn traces" : "Show turn traces"}
            </button>
            <span
              data-testid="poll-status"
              className="text-caption text-content-muted"
            >
              {terminal
                ? "Polling stopped — terminal phase."
                : `Polling every ${DEV_SESSION_POLL_MS / 1000}s.`}
            </span>
          </div>

          {sessionQuery.error && !isNotFound(sessionQuery.error) ? (
            <p
              role="alert"
              data-testid="session-error"
              className="text-body-dense text-status-danger"
            >
              {messageOf(sessionQuery.error)}
            </p>
          ) : null}

          <div className="flex flex-col gap-4 lg:flex-row">
            <div className="min-w-0 flex-1">
              <ChatThread transcript={view.transcript} />
              <TurnComposer
                awaiting={view.awaiting}
                terminal={terminal}
                isSending={postTurn.isPending}
                onSend={handleSend}
                lastUtterance={lastUtterance}
                sendError={turnErrorMessage(postTurn.error)}
              />
            </div>
            <TracePanel
              open={tracesOpen}
              traces={traceQuery.data}
              isLoading={tracesOpen && traceQuery.isPending}
              error={
                traceQuery.error && !isNotFound(traceQuery.error)
                  ? messageOf(traceQuery.error)
                  : null
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}
