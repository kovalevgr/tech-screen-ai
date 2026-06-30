"use client";

// /positions/[id] — edit a Position Template. Prefills from
// usePositionTemplate(id); saves via PATCH sending the full desired selection
// sets (the contract replaces them wholesale). Handles loading and 404.

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import {
  usePositionTemplate,
  useUpdatePositionTemplate,
  parseValidationErrors,
  type PositionTemplateCreate,
} from "@/api/position-templates";
import { ApiError } from "@/api/client";
import {
  PositionForm,
  type PositionFormInitialValues,
} from "@/components/positions/position-form";
import { Card, CardContent } from "@/components/ui/card";
import { positionsUk as t } from "@/messages/positions.uk";

function toInitialValues(
  template: NonNullable<ReturnType<typeof usePositionTemplate>["data"]>
): PositionFormInitialValues {
  return {
    title: template.title,
    level: template.level,
    jdText: template.jd_text ?? "",
    stackIds: template.stack_ids,
    competencyIds: template.competencies.map((c) => c.competency_id),
    mustHaveCompetencyIds: template.competencies
      .filter((c) => c.must_have)
      .map((c) => c.competency_id),
  };
}

export default function EditPositionPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const detail = usePositionTemplate(id);
  const update = useUpdatePositionTemplate(id);
  const [serverErrors, setServerErrors] = React.useState<
    Record<string, string>
  >({});

  function handleSubmit(payload: PositionTemplateCreate) {
    setServerErrors({});
    // PATCH wholesale-replace: send the full desired sets.
    update.mutate(
      {
        title: payload.title,
        level: payload.level,
        jd_text: payload.jd_text,
        stack_ids: payload.stack_ids,
        competency_ids: payload.competency_ids,
        must_have_competency_ids: payload.must_have_competency_ids,
      },
      {
        onSuccess: () => router.push("/positions"),
        onError: (error) => {
          if (error instanceof ApiError && error.status === 422) {
            setServerErrors(parseValidationErrors(error.body));
          }
        },
      }
    );
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
        {t.form.headingEdit}
      </h1>

      {detail.isLoading ? (
        <Card>
          <CardContent className="p-6">
            <div
              className="flex flex-col gap-5"
              aria-busy="true"
              aria-label={t.form.loadingLabel}
            >
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-10 w-full animate-pulse rounded-md bg-surface-muted"
                  aria-hidden="true"
                />
              ))}
            </div>
          </CardContent>
        </Card>
      ) : detail.isError || !detail.data ? (
        <Card>
          <CardContent className="p-6">
            <p className="text-body text-status-danger" role="alert">
              {detail.error instanceof ApiError && detail.error.status === 404
                ? t.form.notFound
                : t.error.generic}
            </p>
          </CardContent>
        </Card>
      ) : (
        <PositionForm
          mode="edit"
          initialValues={toInitialValues(detail.data)}
          onSubmit={handleSubmit}
          onCancel={() => router.push("/positions")}
          isSubmitting={update.isPending}
          serverErrors={serverErrors}
        />
      )}
    </div>
  );
}
