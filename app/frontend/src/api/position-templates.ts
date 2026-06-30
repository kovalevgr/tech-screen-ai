// React Query hooks for Position Template CRUD.
//
// Thin wrappers over the typed openapi-fetch client. Mutations invalidate the
// list (and the affected item) so the UI reflects create / edit / archive
// without a manual reload (FR-007). The PATCH sends the full desired selection
// sets — the contract replaces them wholesale (research §7).

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient, ApiError } from "./client";
import type { components } from "./schema";

export type PositionTemplateRead =
  components["schemas"]["PositionTemplateRead"];
export type PositionTemplateCreate =
  components["schemas"]["PositionTemplateCreate"];
export type PositionTemplateUpdate =
  components["schemas"]["PositionTemplateUpdate"];

export const positionTemplateKeys = {
  all: ["position-templates"] as const,
  list: (includeArchived: boolean) =>
    ["position-templates", "list", { includeArchived }] as const,
  detail: (id: string) => ["position-templates", "detail", id] as const,
};

export function usePositionTemplates(includeArchived: boolean) {
  return useQuery({
    queryKey: positionTemplateKeys.list(includeArchived),
    queryFn: async (): Promise<PositionTemplateRead[]> => {
      const { data, error, response } = await apiClient.GET(
        "/position-templates",
        { params: { query: { include_archived: includeArchived } } }
      );
      if (error || !data) {
        throw new ApiError(
          response.status,
          `GET /position-templates failed (${response.status})`,
          error
        );
      }
      return data;
    },
  });
}

export function usePositionTemplate(id: string | undefined) {
  return useQuery({
    queryKey: positionTemplateKeys.detail(id ?? ""),
    enabled: Boolean(id),
    queryFn: async (): Promise<PositionTemplateRead> => {
      const { data, error, response } = await apiClient.GET(
        "/position-templates/{template_id}",
        { params: { path: { template_id: id as string } } }
      );
      if (error || !data) {
        throw new ApiError(
          response.status,
          `GET /position-templates/${id} failed (${response.status})`,
          error
        );
      }
      return data;
    },
  });
}

export function useCreatePositionTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      body: PositionTemplateCreate
    ): Promise<PositionTemplateRead> => {
      const { data, error, response } = await apiClient.POST(
        "/position-templates",
        { body }
      );
      if (error || !data) {
        throw new ApiError(
          response.status,
          `POST /position-templates failed (${response.status})`,
          error
        );
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: positionTemplateKeys.all });
    },
  });
}

export function useUpdatePositionTemplate(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      body: PositionTemplateUpdate
    ): Promise<PositionTemplateRead> => {
      const { data, error, response } = await apiClient.PATCH(
        "/position-templates/{template_id}",
        { params: { path: { template_id: id } }, body }
      );
      if (error || !data) {
        throw new ApiError(
          response.status,
          `PATCH /position-templates/${id} failed (${response.status})`,
          error
        );
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: positionTemplateKeys.all });
      queryClient.invalidateQueries({
        queryKey: positionTemplateKeys.detail(id),
      });
    },
  });
}

export function useArchivePositionTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string): Promise<PositionTemplateRead> => {
      const { data, error, response } = await apiClient.DELETE(
        "/position-templates/{template_id}",
        { params: { path: { template_id: id } } }
      );
      if (error || !data) {
        throw new ApiError(
          response.status,
          `DELETE /position-templates/${id} failed (${response.status})`,
          error
        );
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: positionTemplateKeys.all });
    },
  });
}

// Parse a FastAPI 422 body into a map of field-name → first message, so the
// form can surface server validation next to the offending field (FR-006).
export function parseValidationErrors(
  body: unknown
): Record<string, string> {
  const out: Record<string, string> = {};
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    Array.isArray((body as { detail: unknown }).detail)
  ) {
    const detail = (body as { detail: components["schemas"]["ValidationError"][] })
      .detail;
    for (const item of detail) {
      // loc is e.g. ["body", "competency_ids", 0]; take the last string segment
      // that names a field.
      const field = [...item.loc]
        .reverse()
        .find((seg): seg is string => typeof seg === "string" && seg !== "body");
      const key = field ?? "_form";
      if (!(key in out)) out[key] = item.msg;
    }
  }
  return out;
}
