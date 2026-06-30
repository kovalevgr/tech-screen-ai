"use client";

// /positions/new — create a Position Template. Renders PositionForm in create
// mode; on success returns to the list (the mutation invalidates the list
// cache so the new row is present). A server 422 is mapped to inline field
// errors via parseValidationErrors.

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  useCreatePositionTemplate,
  parseValidationErrors,
  type PositionTemplateCreate,
} from "@/api/position-templates";
import { ApiError } from "@/api/client";
import { PositionForm } from "@/components/positions/position-form";
import { positionsUk as t } from "@/messages/positions.uk";

export default function NewPositionPage() {
  const router = useRouter();
  const create = useCreatePositionTemplate();
  const [serverErrors, setServerErrors] = React.useState<
    Record<string, string>
  >({});

  function handleSubmit(payload: PositionTemplateCreate) {
    setServerErrors({});
    create.mutate(payload, {
      onSuccess: () => router.push("/positions"),
      onError: (error) => {
        if (error instanceof ApiError && error.status === 422) {
          setServerErrors(parseValidationErrors(error.body));
        }
      },
    });
  }

  return (
    <div className="mx-auto max-w-screen-xl p-6">
      <Link
        href="/positions"
        className="text-body-dense font-medium text-brand-link hover:text-brand-link-hover"
      >
        {t.form.back}
      </Link>
      <h1 className="mb-5 mt-3 text-headline font-semibold text-content-primary">
        {t.form.headingCreate}
      </h1>
      <PositionForm
        mode="create"
        onSubmit={handleSubmit}
        onCancel={() => router.push("/positions")}
        isSubmitting={create.isPending}
        serverErrors={serverErrors}
      />
    </div>
  );
}
