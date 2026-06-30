// MSW request handlers for the Position Templates + active rubric endpoints.
//
// The default export is the happy-path set used by most tests; the named
// helpers build error responses (404/401/403/422) that a test can pass to
// `server.use(...)` to override a single scenario. URLs are matched with a
// leading `*` wildcard so they work regardless of NEXT_PUBLIC_API_BASE_URL.

import { http, HttpResponse } from "msw";

import {
  activeTemplate,
  archivedTemplate,
  rubricFixture,
  TEMPLATE_ACTIVE_ID,
} from "./fixtures";
import type { PositionTemplateRead } from "@/api/position-templates";

const LIST = "*/position-templates";
const ITEM = "*/position-templates/:templateId";
const RUBRIC = "*/rubric/active";

// In-memory store so create/edit/archive are observable across requests in a
// single test. Reset by `resetStore()` from the jest setup's afterEach.
let store: PositionTemplateRead[] = [];

export function resetStore() {
  store = [
    { ...activeTemplate, competencies: [...activeTemplate.competencies] },
    { ...archivedTemplate, competencies: [...archivedTemplate.competencies] },
  ];
}
resetStore();

export const handlers = [
  http.get(RUBRIC, () => HttpResponse.json(rubricFixture)),

  http.get(LIST, ({ request }) => {
    const url = new URL(request.url);
    const includeArchived = url.searchParams.get("include_archived") === "true";
    const rows = includeArchived
      ? store
      : store.filter((t) => t.archived_at === null);
    return HttpResponse.json(rows);
  }),

  http.get(ITEM, ({ params }) => {
    const row = store.find((t) => t.id === params.templateId);
    if (!row) return HttpResponse.json({ detail: "Not Found" }, { status: 404 });
    return HttpResponse.json(row);
  }),

  http.post(LIST, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const created: PositionTemplateRead = {
      id: `created-${store.length + 1}`,
      title: String(body.title ?? ""),
      level: body.level as PositionTemplateRead["level"],
      jd_text: (body.jd_text as string | null) ?? null,
      archived_at: null,
      created_at: "2026-06-30T00:00:00Z",
      created_by: null,
      stack_ids: (body.stack_ids as string[]) ?? [],
      competencies: ((body.competency_ids as string[]) ?? []).map((cid) => ({
        competency_id: cid,
        must_have: ((body.must_have_competency_ids as string[]) ?? []).includes(
          cid
        ),
      })),
    };
    store.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.patch(ITEM, async ({ params, request }) => {
    const idx = store.findIndex((t) => t.id === params.templateId);
    if (idx === -1)
      return HttpResponse.json({ detail: "Not Found" }, { status: 404 });
    const body = (await request.json()) as Record<string, unknown>;
    const prev = store[idx];
    const next: PositionTemplateRead = {
      ...prev,
      title: body.title !== undefined ? String(body.title) : prev.title,
      level:
        body.level !== undefined
          ? (body.level as PositionTemplateRead["level"])
          : prev.level,
      jd_text:
        body.jd_text !== undefined
          ? ((body.jd_text as string | null) ?? null)
          : prev.jd_text,
      stack_ids:
        body.stack_ids !== undefined
          ? (body.stack_ids as string[])
          : prev.stack_ids,
      competencies:
        body.competency_ids !== undefined
          ? (body.competency_ids as string[]).map((cid) => ({
              competency_id: cid,
              must_have: (
                (body.must_have_competency_ids as string[]) ?? []
              ).includes(cid),
            }))
          : prev.competencies,
    };
    store[idx] = next;
    return HttpResponse.json(next);
  }),

  http.delete(ITEM, ({ params }) => {
    const idx = store.findIndex((t) => t.id === params.templateId);
    if (idx === -1)
      return HttpResponse.json({ detail: "Not Found" }, { status: 404 });
    const archived = {
      ...store[idx],
      archived_at: "2026-06-30T00:00:00Z",
    };
    store[idx] = archived;
    return HttpResponse.json(archived);
  }),
];

// --- Per-scenario override helpers -----------------------------------------

export function listStatusHandler(status: number) {
  return http.get(LIST, () =>
    HttpResponse.json({ detail: "error" }, { status })
  );
}

export function rubricStatusHandler(status: number) {
  return http.get(RUBRIC, () =>
    HttpResponse.json({ detail: "error" }, { status })
  );
}

// A 422 on create, mimicking FastAPI's validation-error envelope, with the
// error located on `competency_ids`.
export function createValidationErrorHandler() {
  return http.post(LIST, () =>
    HttpResponse.json(
      {
        detail: [
          {
            loc: ["body", "competency_ids"],
            msg: "List should have at least 1 item after validation, not 0",
            type: "too_short",
          },
        ],
      },
      { status: 422 }
    )
  );
}

export function getItemNotFoundHandler() {
  return http.get(ITEM, () =>
    HttpResponse.json({ detail: "Not Found" }, { status: 404 })
  );
}

export { TEMPLATE_ACTIVE_ID };
