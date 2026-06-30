"use client";

// PositionTable — the list of Position Templates with row actions and the
// archive-confirm dialog. Renders loaded / loading / empty / error states.
// Tokens-only styling per docs/design/screens/16-recruiter-positions/spec.md.

import * as React from "react";
import Link from "next/link";

import {
  usePositionTemplates,
  useArchivePositionTemplate,
  type PositionTemplateRead,
} from "@/api/position-templates";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/cn";
import { positionsUk as t } from "@/messages/positions.uk";

const COLUMN_HEADER_CLASS =
  "text-small font-medium uppercase tracking-[0.04em] text-content-muted";

function StatusPill({ archived }: { archived: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-1 text-small font-medium",
        archived
          ? "bg-status-neutral-subtle text-status-neutral"
          : "bg-surface-muted text-content-secondary"
      )}
    >
      {archived ? t.status.archived : t.status.active}
    </span>
  );
}

function CountColumns({ template }: { template: PositionTemplateRead }) {
  return (
    <>
      <TableCell className="tabular-nums text-content-secondary">
        {template.stack_ids.length}
      </TableCell>
      <TableCell className="tabular-nums text-content-secondary">
        {template.competencies.length}
      </TableCell>
    </>
  );
}

function LoadingRows() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <TableRow key={i}>
          {[0, 1, 2, 3, 4, 5].map((c) => (
            <TableCell key={c}>
              <div
                className="h-4 w-full max-w-32 animate-pulse rounded-sm bg-surface-muted"
                aria-hidden="true"
              />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

function ErrorPanel({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  let message: string = t.error.generic;
  if (error instanceof ApiError) {
    if (error.status === 404) message = t.error.unavailable;
    else if (error.status === 401) message = t.error.signIn;
    else if (error.status === 403) message = t.error.forbidden;
  }
  // A 401/403/404 is a terminal "unavailable" state; only a generic failure
  // offers a retry.
  const showRetry = message === t.error.generic;
  return (
    <Card>
      <CardContent className="flex flex-col items-start gap-4 p-6">
        <p className="text-body text-content-secondary" role="alert">
          {message}
        </p>
        {showRetry ? (
          <Button variant="outline" onClick={onRetry}>
            {t.error.retry}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
        <h2 className="text-title font-semibold text-content-primary">
          {t.empty.heading}
        </h2>
        <p className="max-w-[64ch] text-body text-content-secondary">
          {t.empty.prose}
        </p>
        <Button asChild className="mt-2">
          <Link href="/positions/new">{t.newCta}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export function PositionTable({
  includeArchived,
}: {
  includeArchived: boolean;
}) {
  const query = usePositionTemplates(includeArchived);
  const archive = useArchivePositionTemplate();
  const [pendingArchive, setPendingArchive] =
    React.useState<PositionTemplateRead | null>(null);

  function confirmArchive() {
    if (!pendingArchive) return;
    archive.mutate(pendingArchive.id, {
      onSettled: () => setPendingArchive(null),
    });
  }

  if (query.isError) {
    return <ErrorPanel error={query.error} onRetry={() => query.refetch()} />;
  }

  const templates = query.data ?? [];
  if (!query.isLoading && templates.length === 0) {
    return <EmptyState />;
  }

  return (
    <>
      <Card>
        <CardHeader className="sr-only">
          <CardTitle>{t.pageTitle}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className={COLUMN_HEADER_CLASS}>
                  {t.columns.title}
                </TableHead>
                <TableHead className={COLUMN_HEADER_CLASS}>
                  {t.columns.level}
                </TableHead>
                <TableHead className={COLUMN_HEADER_CLASS}>
                  {t.columns.stacks}
                </TableHead>
                <TableHead className={COLUMN_HEADER_CLASS}>
                  {t.columns.competencies}
                </TableHead>
                <TableHead className={COLUMN_HEADER_CLASS}>
                  {t.columns.status}
                </TableHead>
                <TableHead className={cn(COLUMN_HEADER_CLASS, "text-right")}>
                  {t.columns.actions}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isLoading ? (
                <LoadingRows />
              ) : (
                templates.map((template) => {
                  const archived = template.archived_at !== null;
                  return (
                    <TableRow key={template.id}>
                      <TableCell className="font-medium text-content-primary">
                        {template.title}
                      </TableCell>
                      <TableCell className="text-content-secondary">
                        {template.level}
                      </TableCell>
                      <CountColumns template={template} />
                      <TableCell>
                        <StatusPill archived={archived} />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/positions/${template.id}`}>
                              {t.rowActions.edit}
                            </Link>
                          </Button>
                          {archived ? null : (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setPendingArchive(template)}
                            >
                              {t.rowActions.archive}
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog
        open={pendingArchive !== null}
        onOpenChange={(open) => {
          if (!open) setPendingArchive(null);
        }}
      >
        <DialogContent className="rounded-xl">
          <DialogHeader>
            <DialogTitle>{t.archive.title}</DialogTitle>
            <DialogDescription>{t.archive.body}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPendingArchive(null)}
              disabled={archive.isPending}
            >
              {t.archive.cancel}
            </Button>
            <Button onClick={confirmArchive} disabled={archive.isPending}>
              {t.archive.confirm}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
