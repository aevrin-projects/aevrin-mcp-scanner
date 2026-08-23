import { request } from "@/shared/api";
import type { AccountUsage } from "../model/types";

export const usageApi = {
  getUsage: () => request<AccountUsage>("/account/usage"),
};
