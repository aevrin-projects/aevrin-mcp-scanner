import { request } from "@/shared/api";
import type { BulkFixResponse, Finding } from "../model/types";

export const findingApi = {
  getScanFindings: (scanId: string) => request<Finding[]>(`/scans/${scanId}/findings`),
  getFinding: (id: string) => request<Finding>(`/findings/${id}`),
  triageFinding: (id: string, triage_status: string, reason?: string) =>
    request<Finding>(`/findings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ triage_status, reason }),
    }),
  fixFinding: (findingId: string) =>
    request<{ status: string; pr_url: string | null; failure_reason: string | null; install_url: string | null }>(
      `/findings/${findingId}/fix`,
      { method: "POST" },
    ),
  fixScan: (scanId: string) => request<BulkFixResponse>(`/scans/${scanId}/fix`, { method: "POST" }),
  cancelScanFix: (scanId: string) =>
    request<{ cancelled: boolean; released: number }>(`/scans/${scanId}/fix/cancel`, { method: "POST" }),
};
