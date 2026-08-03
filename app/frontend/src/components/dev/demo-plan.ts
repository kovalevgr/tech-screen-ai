// Prefill for the dev console's plan textarea (FR-034-1).
//
// Shape: state-machine contract §7 ("Plan shape consumed") — until the Planner
// (T24/T25) ships, dev sessions run on hand-written plans like this one.
// Synthetic content only; no candidate data (spec 034 Clarification 3).

import type { PlanSnapshot } from "@/api/dev-session";

export const DEMO_PLAN: PlanSnapshot = {
  plan_version: 1,
  competencies: [
    {
      node_id: "py.async",
      label_uk: "Асинхронний Python",
      target_level: 3,
      minutes: 12,
      seed_questions_uk: [
        "Розкажіть, як працює event loop в asyncio і що відбувається під час await.",
      ],
      probe_branches_uk: [
        "Що станеться, якщо всередині корутини викликати блокуючу операцію?",
      ],
    },
    {
      node_id: "db.transactions",
      label_uk: "Транзакції та рівні ізоляції",
      target_level: 3,
      minutes: 10,
      seed_questions_uk: [
        "Які рівні ізоляції транзакцій ви використовували і чому саме такі?",
      ],
      probe_branches_uk: [],
    },
  ],
  qa_minutes: 5,
  session_max_minutes: 60,
};

export const DEMO_PLAN_JSON = JSON.stringify(DEMO_PLAN, null, 2);
