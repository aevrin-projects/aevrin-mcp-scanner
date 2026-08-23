import { API_URL, ApiError, request } from "@/shared/api";

export const deviceApi = {
  approveDevice: (userCode: string, fingerprint: string | null) =>
    request<{ status: string }>(`/device/${userCode}/approve`, {
      method: "POST",
      body: JSON.stringify({ user_code: userCode, fingerprint }),
    }),
  /** GET /device/{code} is unauthenticated on purpose: the approval page has
   *  to show what is pending before the person is necessarily signed in. */
  getDeviceCodeInfo: async (userCode: string): Promise<{ client_kind: string; status: string }> => {
    const res = await fetch(`${API_URL}/device/${userCode}`);
    if (!res.ok) {
      throw new ApiError(res.status, res.status === 404 ? "This code is invalid or has expired." : res.statusText);
    }
    return res.json();
  },
};
