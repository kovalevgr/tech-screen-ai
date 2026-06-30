// React Query hook for the active rubric snapshot.
//
// The form's stack / competency pickers are populated from here, so the
// recruiter never types ids (FR-003). Read-only; no mutations.

import { useQuery } from "@tanstack/react-query";

import { apiClient, ApiError } from "./client";
import type { components } from "./schema";

export type RubricSnapshot = components["schemas"]["RubricSnapshot"];

export const rubricKeys = {
  active: ["rubric", "active"] as const,
};

export function useActiveRubric() {
  return useQuery({
    queryKey: rubricKeys.active,
    queryFn: async (): Promise<RubricSnapshot> => {
      // `/rubric/active` declares no error responses in the contract, so
      // openapi-fetch types `error` as `never`; we still guard on the HTTP
      // status + presence of data to surface 401/403/404 the running backend
      // may return at runtime.
      const { data, response } = await apiClient.GET("/rubric/active");
      if (!response.ok || !data) {
        throw new ApiError(
          response.status,
          `GET /rubric/active failed (${response.status})`,
          data ?? null
        );
      }
      return data;
    },
  });
}
