// Shared fixtures for the MSW handlers — a small active rubric and a couple of
// position templates (one active, one archived). Ids are stable so tests can
// assert against them.

import type { RubricSnapshot } from "@/api/rubric";
import type { PositionTemplateRead } from "@/api/position-templates";

// Rubric: two stacks, each with one competency block holding competencies.
export const STACK_BACKEND = "11111111-1111-1111-1111-111111111111";
export const STACK_FRONTEND = "22222222-2222-2222-2222-222222222222";

export const COMP_PYTHON = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
export const COMP_DATABASES = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
export const COMP_REACT = "cccccccc-cccc-cccc-cccc-cccccccccccc";
export const COMP_CSS = "dddddddd-dddd-dddd-dddd-dddddddddddd";

export const rubricFixture: RubricSnapshot = {
  rubric_tree_version_id: "99999999-9999-9999-9999-999999999999",
  label: "Rubric v1",
  stacks: [
    {
      id: STACK_BACKEND,
      name: "Backend",
      competency_blocks: [
        {
          id: "blk-be-1",
          name: "Core",
          position: 1,
          competencies: [
            { id: COMP_PYTHON, name: "Python", topics: [], levels: [] },
            { id: COMP_DATABASES, name: "Databases", topics: [], levels: [] },
          ],
        },
      ],
    },
    {
      id: STACK_FRONTEND,
      name: "Frontend",
      competency_blocks: [
        {
          id: "blk-fe-1",
          name: "Core",
          position: 1,
          competencies: [
            { id: COMP_REACT, name: "React", topics: [], levels: [] },
            { id: COMP_CSS, name: "CSS", topics: [], levels: [] },
          ],
        },
      ],
    },
  ],
};

export const TEMPLATE_ACTIVE_ID = "33333333-3333-3333-3333-333333333333";
export const TEMPLATE_ARCHIVED_ID = "44444444-4444-4444-4444-444444444444";

export const activeTemplate: PositionTemplateRead = {
  id: TEMPLATE_ACTIVE_ID,
  title: "Senior Backend Engineer",
  level: "Senior",
  jd_text: "Будуємо платіжну платформу.",
  archived_at: null,
  created_at: "2026-06-01T10:00:00Z",
  created_by: null,
  stack_ids: [STACK_BACKEND],
  competencies: [
    { competency_id: COMP_PYTHON, must_have: true },
    { competency_id: COMP_DATABASES, must_have: false },
  ],
};

export const archivedTemplate: PositionTemplateRead = {
  id: TEMPLATE_ARCHIVED_ID,
  title: "Legacy Frontend Role",
  level: "Middle",
  jd_text: null,
  archived_at: "2026-05-15T09:00:00Z",
  created_at: "2026-04-01T10:00:00Z",
  created_by: null,
  stack_ids: [STACK_FRONTEND],
  competencies: [{ competency_id: COMP_REACT, must_have: false }],
};
