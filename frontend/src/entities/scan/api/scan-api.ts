import { request } from "@/shared/api";
import type { Scan, ScanDiff, ScanStage } from "../model/types";

export const scanApi = {
  createScan: (target_type: string, target: string) =>
    request<Scan>("/scans", { method: "POST", body: JSON.stringify({ target_type, target }) }),
  listScans: () => request<Scan[]>("/scans"),
  getScan: (id: string) => request<Scan>(`/scans/${id}`),
  /** Stop a scan that is still open so it can be read and deleted. Ends the
   *  record rather than interrupting the worker; a cancelled scan never
   *  carries a grade. */
  cancelScan: (id: string) =>
    request<{ status: string; detail: string }>(`/scans/${id}/cancel`, { method: "POST" }),
  deleteScan: (id: string) => request<void>(`/scans/${id}`, { method: "DELETE" }),
  clearScanHistory: () => request<void>("/scans", { method: "DELETE" }),
  getScanStages: (id: string) => request<ScanStage[]>(`/scans/${id}/stages`),
  getScanDiff: (id: string) => request<ScanDiff>(`/scans/${id}/diff`),
  exportReport: (id: string) => request<{ url: string }>(`/scans/${id}/export`),
};
