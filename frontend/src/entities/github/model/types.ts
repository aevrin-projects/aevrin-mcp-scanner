/** One repository the connected GitHub App installation can reach.
 *  `looks_like_mcp` is a label, never a gate: `null` means the check could
 *  not run, and `false` only means the heuristic didn't recognise it, the
 *  repo is still scannable. */
export type GithubRepo = {
  full_name: string;
  html_url: string;
  private: boolean;
  default_branch: string;
  pushed_at: string | null;
  looks_like_mcp: boolean | null;
};

export type GithubReposResponse = {
  connected: boolean;
  account_login: string | null;
  repos: GithubRepo[];
};
