import { request } from "@/shared/api";
import type { Finding } from "../model/types";

export const findingApi = {
  getScanFindings: (scanId: string) => request<Finding[]>(`/scans/${scanId}/findings`),
  getFinding: (id: string) => request<Finding>(`/findings/${id}`),
  triageFinding: (id: string, triage_status: string, reason?: string) =>
    request<Finding>(`/findings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ triage_status, reason }),
    }),
};
