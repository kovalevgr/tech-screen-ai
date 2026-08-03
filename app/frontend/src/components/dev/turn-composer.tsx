"use client";

// Candidate-turn composer (FR-034-1).
//
// The input is enabled ONLY while `SessionView.awaiting == "candidate"`. Every
// other state (awaiting the interviewer, awaiting nobody, terminal phase) is a
// disabled input plus a plain sentence saying which one it is — the machine
// owns turn-taking, the UI never guesses that it may be the candidate's move.
//
// The raw `utterance` field of the last POST /turns response is echoed under
// the composer: it is a contract field and null carries meaning (the session
// ended on that turn), so it is shown rather than silently dropped.

import * as React from "react";

import type { DevAwaiting } from "@/api/dev-session";

export function TurnComposer({
  awaiting,
  terminal,
  isSending,
  onSend,
  lastUtterance,
  sendError,
}: {
  awaiting: DevAwaiting;
  terminal: boolean;
  isSending: boolean;
  onSend: (text: string) => Promise<unknown>;
  lastUtterance: string | null | undefined;
  sendError: string | null;
}) {
  const [text, setText] = React.useState("");

  const canSend = awaiting === "candidate" && !terminal && !isSending;

  let hint: string;
  if (terminal) {
    hint = "Session is terminal — no further candidate turns are accepted.";
  } else if (awaiting === "candidate") {
    hint = "The machine is awaiting a candidate turn.";
  } else if (awaiting === "interviewer") {
    hint = "Waiting for the interviewer — polling for the reply.";
  } else {
    hint = "Not awaiting a candidate turn.";
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = text.trim();
    if (!canSend || value.length === 0) return;
    try {
      await onSend(value);
      setText("");
    } catch {
      // The parent renders the failure from the mutation state; keep the typed
      // text so the turn can be retried.
    }
  }

  return (
    <form onSubmit={handleSubmit} data-testid="turn-composer" className="mt-4">
      <label
        htmlFor="dev-turn"
        className="block text-body-dense font-semibold text-content-primary"
      >
        Candidate turn
      </label>
      <p data-testid="turn-hint" className="mt-1 text-caption text-content-muted">
        {hint}
      </p>
      <textarea
        id="dev-turn"
        name="turn"
        rows={3}
        disabled={!canSend}
        value={text}
        onChange={(event) => setText(event.target.value)}
        className="mt-2 w-full rounded-md border border-border-default bg-surface-base p-3 text-body-dense text-content-primary disabled:bg-surface-muted disabled:text-content-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      />
      <button
        type="submit"
        disabled={!canSend}
        className="mt-2 rounded-md border border-border-strong bg-surface-muted px-4 py-2 text-body-dense font-semibold text-content-primary disabled:text-content-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      >
        {isSending ? "Sending…" : "Send turn"}
      </button>

      {sendError ? (
        <p
          role="alert"
          data-testid="turn-error"
          className="mt-2 text-body-dense text-status-danger"
        >
          {sendError}
        </p>
      ) : null}

      {lastUtterance !== undefined ? (
        <p
          data-testid="last-utterance"
          className="mt-3 font-mono text-caption text-content-muted"
        >
          utterance:{" "}
          {lastUtterance === null
            ? "null — the session ended on this turn"
            : lastUtterance}
        </p>
      ) : null}
    </form>
  );
}
