import { request } from "@/shared/api";
import type { Scan, ScanDiff, ScanStage } from "../model/types";

export const scanApi = {
  createScan: (target_type: string, target: string) =>
    request<Scan>("/scans", { method: "POST", body: JSON.stringify({ target_type, target }) }),
  listScans: () => request<Scan[]>("/scans"),
  getScan: (id: string) => request<Scan>(`/scans/${id}`),
  deleteScan: (id: string) => request<void>(`/scans/${id}`, { method: "DELETE" }),
  clearScanHistory: () => request<void>("/scans", { method: "DELETE" }),
  getScanStages: (id: string) => request<ScanStage[]>(`/scans/${id}/stages`),
  getScanDiff: (id: string) => request<ScanDiff>(`/scans/${id}/diff`),
  exportReport: (id: string) => request<{ url: string }>(`/scans/${id}/export`),
};
