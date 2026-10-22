const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include", // send httpOnly cookies
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────
export const authApi = {
  getLoginUrl: () => request<{ url: string }>("/api/auth/discord/login"),
  callback: (code: string) =>
    request("/api/auth/discord/callback", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  me: () => request("/api/auth/me"),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  refresh: () => request("/api/auth/refresh", { method: "POST" }),
};

// ── Profile ───────────────────────────────────────────────
export const profileApi = {
  get: () => request<{ profile: Record<string, unknown> | null }>("/api/profile"),
  patch: (data: Record<string, unknown>) =>
    request<{ profile: Record<string, unknown> | null }>("/api/profile", { method: "PATCH", body: JSON.stringify(data) }),
  uploadResume: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_URL}/api/profile/resume`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? "Upload failed");
    }
    return res.json();
  },
  getQuestions: () => request<{ questions: unknown[] }>("/api/profile/questions"),
  submitAnswers: (answers: { question_id: string; answer: string }[]) =>
    request("/api/profile/answers", { method: "POST", body: JSON.stringify(answers) }),
};

// ── Jobs ──────────────────────────────────────────────────
export const jobsApi = {
  list: (params?: { page?: number; limit?: number; min_score?: number }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.min_score) q.set("min_score", String(params.min_score));
    return request<{ items: unknown[]; total: number }>(`/api/jobs?${q}`);
  },
  get: (id: string) => request(`/api/jobs/${id}`),
  apply: (id: string) => request(`/api/jobs/${id}/apply`, { method: "POST" }),
  fetchNow: () => request<{ ok: boolean; message: string }>("/api/jobs/fetch-now", { method: "POST" }),
};

// ── Settings ──────────────────────────────────────────────
export const settingsApi = {
  get: () => request("/api/settings"),
  update: (data: Record<string, unknown>) =>
    request("/api/settings", { method: "PUT", body: JSON.stringify(data) }),
  testAI: () => request("/api/settings/test-ai", { method: "POST" }),
  getModelSuggestions: () =>
    request<Record<string, string[]>>("/api/settings/models"),
};

// ── Admin ─────────────────────────────────────────────────
export const adminApi = {
  stats: () => request<Record<string, unknown>>("/api/admin/stats"),
  users: () => request<{ users: Array<Record<string, unknown>> }>("/api/admin/users"),
  workflows: () => request<{ runs: Array<Record<string, unknown>> }>("/api/admin/workflows"),
  activity: () => request<{ recent_jobs: Array<Record<string, unknown>>; recent_matches: Array<Record<string, unknown>> }>("/api/admin/activity"),
  updateUser: (userId: string, data: { role?: string; is_active?: boolean }) =>
    request<{ ok: boolean; user: Record<string, unknown> }>(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(data) }),
  triggerDiscovery: () =>
    request<{ ok: boolean; message: string }>("/api/admin/trigger-discovery", { method: "POST" }),
};

// ── Companies ─────────────────────────────────────────────
export interface TargetCompany {
  _id: string;
  name: string;
  grade: string;
  career_page: string;
  ats_type: string;
  board_token?: string;
  api_url?: string;
  industry?: string;
  location_hq?: string;
  is_active: boolean;
  total_jobs_fetched: number;
  last_fetched_at?: string;
  created_at?: string;
  updated_at?: string;
}

export const companiesApi = {
  list: (params?: { grade?: string; search?: string; is_active?: boolean; skip?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.grade && params.grade !== "all") q.set("grade", params.grade);
    if (params?.search) q.set("search", params.search);
    if (params?.is_active !== undefined) q.set("is_active", String(params.is_active));
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    return request<{
      items: TargetCompany[];
      total: number;
      grade_counts: {
        all: number;
        "Tier-1": number;
        "Tier-2": number;
        "Tier-3": number;
        Startup: number;
        active: number;
      };
    }>(`/api/companies?${q}`);
  },
  get: (id: string) => request<TargetCompany>(`/api/companies/${id}`),
  create: (data: {
    name: string;
    grade: string;
    career_page: string;
    ats_type?: string;
    board_token?: string;
    api_url?: string;
    industry?: string;
    location_hq?: string;
    is_active?: boolean;
  }) => request<TargetCompany>("/api/companies", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Partial<TargetCompany>) =>
    request<{ ok: boolean; company: TargetCompany }>(`/api/companies/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id: string) => request<{ ok: boolean; message: string }>(`/api/companies/${id}`, { method: "DELETE" }),
  seed: (force?: boolean) => request<{ ok: boolean; message: string }>(`/api/companies/seed?force=${!!force}`, { method: "POST" }),
};

