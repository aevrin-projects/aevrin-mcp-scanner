import { request } from "@/shared/api";
import type { ApiKey } from "../model/types";

export const apiKeyApi = {
  listApiKeys: () => request<ApiKey[]>("/api-keys"),
  createApiKey: (name: string) =>
    request<{ id: number; name: string; plaintext_key: string }>("/api-keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  revokeApiKey: (id: number) => request<void>(`/api-keys/${id}`, { method: "DELETE" }),
  deleteRevokedApiKeys: () =>
    request<{ deleted: number }>("/api-keys/revoked", { method: "DELETE" }),
};
