"use client";

// PositionForm — create/edit form for a Position Template. Options (stacks,
// competencies) come from the active rubric so the recruiter never types ids
// (FR-003). Competencies are scoped to the selected stacks; each selected
// competency exposes a must-have checkbox. Client validation mirrors the
// contract; server 422 errors are surfaced inline next to the field, input
// preserved (FR-006). If the rubric cannot load, submit is disabled.

import * as React from "react";

import { useActiveRubric, type RubricSnapshot } from "@/api/rubric";
import { type PositionTemplateCreate } from "@/api/position-templates";
import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { positionsUk as t } from "@/messages/positions.uk";

type PositionLevelValue = components["schemas"]["PositionLevel"];

const LEVELS: PositionLevelValue[] = [
  "Junior",
  "Middle",
  "Senior",
  "Tech Leader",
];

export interface PositionFormInitialValues {
  title: string;
  level: PositionLevelValue | "";
  jdText: string;
  stackIds: string[];
  competencyIds: string[];
  mustHaveCompetencyIds: string[];
}

const EMPTY_INITIAL: PositionFormInitialValues = {
  title: "",
  level: "",
  jdText: "",
  stackIds: [],
  competencyIds: [],
  mustHaveCompetencyIds: [],
};

export interface PositionFormProps {
  mode: "create" | "edit";
  initialValues?: PositionFormInitialValues;
  /** Submit the validated, contract-shaped payload. */
  onSubmit: (payload: PositionTemplateCreate) => void;
  onCancel: () => void;
  /** Whether the parent mutation is in flight. */
  isSubmitting?: boolean;
  /** Server-side field errors (field name → message), e.g. from a 422. */
  serverErrors?: Record<string, string>;
}

// Map of competency id → its owning stack id, derived from the rubric tree.
function competencyToStack(rubric: RubricSnapshot): Map<string, string> {
  const map = new Map<string, string>();
  for (const stack of rubric.stacks) {
    for (const block of stack.competency_blocks) {
      for (const comp of block.competencies) {
        map.set(comp.id, stack.id);
      }
    }
  }
  return map;
}

function FormSkeleton() {
  return (
    <div
      className="flex flex-col gap-5"
      aria-busy="true"
      aria-label={t.form.loadingLabel}
    >
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-10 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p className="text-caption text-status-danger" role="alert">
      {message}
    </p>
  );
}

export function PositionForm({
  // `mode` (create | edit) is part of the component contract — callers pass it
  // for intent and a stable test/data hook. The field logic is identical in
  // both modes (edit just arrives with prefilled `initialValues`), so it is not
  // branched on here.
  mode = "create",
  initialValues = EMPTY_INITIAL,
  onSubmit,
  onCancel,
  isSubmitting = false,
  serverErrors = {},
}: PositionFormProps) {
  const rubricQuery = useActiveRubric();

  const [title, setTitle] = React.useState(initialValues.title);
  const [level, setLevel] = React.useState<PositionLevelValue | "">(
    initialValues.level
  );
  const [jdText, setJdText] = React.useState(initialValues.jdText);
  const [stackIds, setStackIds] = React.useState<Set<string>>(
    new Set(initialValues.stackIds)
  );
  const [competencyIds, setCompetencyIds] = React.useState<Set<string>>(
    new Set(initialValues.competencyIds)
  );
  const [mustHaveIds, setMustHaveIds] = React.useState<Set<string>>(
    new Set(initialValues.mustHaveCompetencyIds)
  );
  const [clientErrors, setClientErrors] = React.useState<
    Record<string, string>
  >({});

  const rubric = rubricQuery.data;
  const compStackMap = React.useMemo(
    () => (rubric ? competencyToStack(rubric) : new Map<string, string>()),
    [rubric]
  );

  function toggleStack(stackId: string, checked: boolean) {
    setStackIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(stackId);
      } else {
        next.delete(stackId);
        // Prune competencies (and their must-have flags) that belonged only to
        // the deselected stack.
        setCompetencyIds((prevComps) => {
          const nextComps = new Set(prevComps);
          for (const compId of prevComps) {
            if (compStackMap.get(compId) === stackId) nextComps.delete(compId);
          }
          return nextComps;
        });
        setMustHaveIds((prevMust) => {
          const nextMust = new Set(prevMust);
          for (const compId of prevMust) {
            if (compStackMap.get(compId) === stackId) nextMust.delete(compId);
          }
          return nextMust;
        });
      }
      return next;
    });
  }

  function toggleCompetency(compId: string, checked: boolean) {
    setCompetencyIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(compId);
      } else {
        next.delete(compId);
        // Deselecting a competency clears its must-have flag.
        setMustHaveIds((prevMust) => {
          const nextMust = new Set(prevMust);
          nextMust.delete(compId);
          return nextMust;
        });
      }
      return next;
    });
  }

  function toggleMustHave(compId: string, checked: boolean) {
    setMustHaveIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(compId);
      else next.delete(compId);
      return next;
    });
  }

  function validate(): Record<string, string> {
    const errs: Record<string, string> = {};
    const trimmed = title.trim();
    if (trimmed.length === 0) errs.title = t.form.validation.titleRequired;
    else if (trimmed.length > 200)
      errs.title = t.form.validation.titleTooLong;
    if (level === "") errs.level = t.form.validation.levelRequired;
    if (stackIds.size === 0)
      errs.stack_ids = t.form.validation.stacksRequired;
    if (competencyIds.size === 0)
      errs.competency_ids = t.form.validation.competenciesRequired;
    for (const mustId of mustHaveIds) {
      if (!competencyIds.has(mustId)) {
        errs.must_have_competency_ids = t.form.validation.mustHaveSubset;
        break;
      }
    }
    return errs;
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const errs = validate();
    setClientErrors(errs);
    if (Object.keys(errs).length > 0) return;
    onSubmit({
      title: title.trim(),
      level: level as PositionLevelValue,
      jd_text: jdText.trim() === "" ? null : jdText.trim(),
      stack_ids: Array.from(stackIds),
      competency_ids: Array.from(competencyIds),
      must_have_competency_ids: Array.from(mustHaveIds),
    });
  }

  // Merge client + server errors; server is the source of truth and wins.
  const errors = { ...clientErrors, ...serverErrors };

  if (rubricQuery.isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <FormSkeleton />
        </CardContent>
      </Card>
    );
  }

  const rubricUnavailable = rubricQuery.isError || !rubric;

  return (
    <Card>
      <CardContent className="p-6">
        {rubricUnavailable ? (
          <p className="mb-5 text-body text-status-danger" role="alert">
            {t.form.rubricError}
          </p>
        ) : null}

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5"
          data-mode={mode}
          noValidate
        >
          {/* Title */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="position-title">{t.form.labels.title}</Label>
            <Input
              id="position-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              aria-invalid={Boolean(errors.title)}
            />
            <FieldError message={errors.title} />
          </div>

          {/* Level */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="position-level">{t.form.labels.level}</Label>
            <Select
              value={level === "" ? undefined : level}
              onValueChange={(value) =>
                setLevel(value as PositionLevelValue)
              }
            >
              <SelectTrigger
                id="position-level"
                aria-invalid={Boolean(errors.level)}
              >
                <SelectValue placeholder={t.form.levelPlaceholder} />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((lvl) => (
                  <SelectItem key={lvl} value={lvl}>
                    {lvl}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError message={errors.level} />
          </div>

          {/* JD */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="position-jd">{t.form.labels.jdText}</Label>
            <Textarea
              id="position-jd"
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              className="min-h-32"
            />
          </div>

          {/* Stacks */}
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-body font-medium text-content-primary">
              {t.form.labels.stacks}
            </legend>
            <div className="flex flex-col gap-2">
              {rubric?.stacks.map((stack) => (
                <label
                  key={stack.id}
                  className="flex cursor-pointer items-center gap-2 text-body-dense text-content-secondary"
                >
                  <Checkbox
                    checked={stackIds.has(stack.id)}
                    onCheckedChange={(value) =>
                      toggleStack(stack.id, value === true)
                    }
                  />
                  {stack.name}
                </label>
              ))}
            </div>
            <FieldError message={errors.stack_ids} />
          </fieldset>

          {/* Competencies — scoped to selected stacks */}
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-body font-medium text-content-primary">
              {t.form.labels.competencies}
            </legend>
            <div className="flex flex-col gap-3">
              {rubric?.stacks
                .filter((stack) => stackIds.has(stack.id))
                .map((stack) =>
                  stack.competency_blocks.flatMap((block) =>
                    block.competencies.map((comp) => {
                      const selected = competencyIds.has(comp.id);
                      return (
                        <div
                          key={comp.id}
                          className="flex flex-wrap items-center gap-x-4 gap-y-2"
                        >
                          <label className="flex cursor-pointer items-center gap-2 text-body-dense text-content-secondary">
                            <Checkbox
                              checked={selected}
                              onCheckedChange={(value) =>
                                toggleCompetency(comp.id, value === true)
                              }
                            />
                            {comp.name}
                          </label>
                          {selected ? (
                            <label className="flex cursor-pointer items-center gap-2 text-caption text-content-muted">
                              <Checkbox
                                checked={mustHaveIds.has(comp.id)}
                                onCheckedChange={(value) =>
                                  toggleMustHave(comp.id, value === true)
                                }
                              />
                              {t.form.labels.mustHave}
                            </label>
                          ) : null}
                        </div>
                      );
                    })
                  )
                )}
            </div>
            <FieldError message={errors.competency_ids} />
            <FieldError message={errors.must_have_competency_ids} />
          </fieldset>

          {/* Footer: primary on the right (§13) */}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              {t.form.buttons.cancel}
            </Button>
            <Button type="submit" disabled={isSubmitting || rubricUnavailable}>
              {t.form.buttons.save}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
