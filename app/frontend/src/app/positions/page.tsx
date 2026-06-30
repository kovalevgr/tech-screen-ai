"use client";

// /positions — the Position Templates list. Heading + active count, the
// "+ Нова позиція" CTA (the single primary CTA on this screen), the
// "Показати архівовані" toggle, and the PositionTable (which owns the
// loaded / loading / empty / error states).

import * as React from "react";
import Link from "next/link";

import { usePositionTemplates } from "@/api/position-templates";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { PositionTable } from "@/components/positions/position-table";
import { positionsUk as t } from "@/messages/positions.uk";

export default function PositionsPage() {
  const [includeArchived, setIncludeArchived] = React.useState(false);

  // The count in the heading is always the number of *active* templates,
  // independent of the include-archived toggle.
  const activeQuery = usePositionTemplates(false);
  const activeCount = activeQuery.data?.length ?? 0;

  return (
    <div className="mx-auto max-w-screen-xl p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-headline font-semibold text-content-primary">
            {t.pageTitle}
          </h1>
          {activeQuery.isSuccess ? (
            <span className="text-body-dense text-content-muted">
              {t.countActive(activeCount)}
            </span>
          ) : null}
        </div>
        <Button asChild>
          <Link href="/positions/new">{t.newCta}</Link>
        </Button>
      </div>

      <div className="mt-5 flex items-center gap-2">
        <Checkbox
          id="include-archived"
          checked={includeArchived}
          onCheckedChange={(value) => setIncludeArchived(value === true)}
        />
        <Label htmlFor="include-archived" className="cursor-pointer">
          {t.showArchived}
        </Label>
      </div>

      <div className="mt-4">
        <PositionTable includeArchived={includeArchived} />
      </div>
    </div>
  );
}
