"use client";

// Chat thread for the dev console (FR-034-1).
//
// Renders `SessionView.transcript` verbatim and in order — the transcript is
// the single source of truth for what was said; the console never composes
// messages of its own. The three contract roles (system / interviewer /
// candidate) are labelled and tinted differently so a reader can tell scripted
// text from model text from candidate text at a glance.

import type { TranscriptMessage, TranscriptRole } from "@/api/dev-session";

const ROLE_STYLE: Record<TranscriptRole, string> = {
  system: "border-border-default bg-surface-muted",
  interviewer: "border-status-info bg-status-info-subtle",
  candidate: "border-border-strong bg-surface-base",
};

export function ChatThread({
  transcript,
}: {
  transcript: TranscriptMessage[];
}) {
  if (transcript.length === 0) {
    return (
      <p data-testid="chat-thread-empty" className="text-body-dense text-content-muted">
        No messages yet.
      </p>
    );
  }

  return (
    <ol data-testid="chat-thread" className="flex flex-col gap-3">
      {transcript.map((message, index) => (
        <li
          key={`${message.turn_id ?? "no-turn"}-${index}`}
          data-testid="chat-message"
          data-role={message.role}
          className={`rounded-md border p-3 ${ROLE_STYLE[message.role]}`}
        >
          <p className="font-mono text-small uppercase text-content-muted">
            {message.role}
            {message.turn_id ? ` · turn ${message.turn_id}` : ""}
          </p>
          <p className="mt-1 max-w-prose whitespace-pre-wrap text-body text-content-primary">
            {message.text}
          </p>
        </li>
      ))}
    </ol>
  );
}
