import { request } from "@/shared/api";
import type { GithubReposResponse } from "../model/types";

export const githubApi = {
  getStatus: () => request<{ connected: boolean; account_login: string | null }>("/github/status"),
  getInstallUrl: () => request<{ url: string }>("/github/install-url"),
  // labels=false skips the per-repo MCP heuristic. The picker wants the
  // labels; the Fix It access check only needs the names, and shouldn't wait
  // on ~180 GitHub calls to decide whether to enable a button.
  getRepos: (labels = true) => request<GithubReposResponse>(`/github/repos?labels=${labels}`),
};
