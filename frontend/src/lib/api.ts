const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "http://localhost:8000";

let isRefreshingToken = false;
let refreshPromise: Promise<boolean> | null = null;

async function fetchWithTimeout(url: string, options?: RequestInit, timeoutMs = 20000): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(new Error("Request timed out")), timeoutMs);
  try {
    const res = await fetch(url, {
      ...options,
      signal: options?.signal ?? controller.signal,
    });
    return res;
  } finally {
    clearTimeout(id);
  }
}

async function doTokenRefresh(): Promise<boolean> {
  if (isRefreshingToken && refreshPromise) return refreshPromise;
  isRefreshingToken = true;
  refreshPromise = (async () => {
    try {
      const res = await fetchWithTimeout(`${API_URL}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
      }, 8000);
      return res.ok;
    } catch {
      return false;
    } finally {
      isRefreshingToken = false;
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res = await fetchWithTimeout(`${API_URL}${path}`, {
    credentials: "include", // send httpOnly cookies
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  // Transparently refresh token and retry if 401 Unauthorized
  if (
    res.status === 401 &&
    !path.includes("/auth/refresh") &&
    !path.includes("/auth/discord") &&
    !path.includes("/auth/dev-login") &&
    !path.includes("/auth/test-login") &&
    !path.includes("/auth/logout")
  ) {
    const refreshed = await doTokenRefresh();
    if (refreshed) {
      res = await fetchWithTimeout(`${API_URL}${path}`, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...options?.headers },
        ...options,
      });
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────
export interface TestPersona {
  id: string;
  name: string;
  email: string;
  role: string;
  category: string;
  title: string;
  badge_color: string;
  avatar_letter: string;
  location: string;
  target_titles: string[];
  summary: string;
  skills: Record<string, string[]>;
}

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
  devLogin: () => request<{ ok: boolean; user: Record<string, unknown> }>("/api/auth/dev-login", { method: "POST" }),
  getTestPersonas: () => request<{ personas: TestPersona[] }>("/api/auth/test-personas"),
  testLogin: (persona_id: string) =>
    request<{ ok: boolean; user: Record<string, unknown>; persona: TestPersona }>("/api/auth/test-login", {
      method: "POST",
      body: JSON.stringify({ persona_id }),
    }),
};

// ── Profile ───────────────────────────────────────────────
export type ScreeningQuestionType = "multiselect" | "single_select" | "boolean" | "number" | "text";

export interface ScreeningQuestion {
  id: string;
  category?: string;
  type?: ScreeningQuestionType;
  question: string;
  context_hint?: string;
  suggested_options?: string[];
  unit?: string;
  min_selections?: number;
  max_selections?: number;
  answer?: string | string[] | number | boolean | null;
  answered_at?: string | null;
}

export interface ScreeningQAItem {
  id: string;
  question: string;
  answer: string;
  raw_answer?: unknown;
  type?: ScreeningQuestionType;
  category?: string;
  target_role?: string;
  answered_at: string;
}

export interface ScreeningData {
  target_roles: string[];
  selected_role: string | null;
  questions: ScreeningQuestion[];
  qa_history: ScreeningQAItem[];
}

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
    return res.json() as Promise<{
      ok: boolean;
      is_analyzing: boolean;
      message: string;
      filename: string;
      profile?: Record<string, unknown>;
    }>;
  },
  getQuestions: () => request<{ questions: unknown[] }>("/api/profile/questions"),
  submitAnswers: (answers: { question_id: string; answer: string }[]) =>
    request("/api/profile/answers", { method: "POST", body: JSON.stringify(answers) }),
  getScreening: () => request<ScreeningData>("/api/profile/screening"),
  selectScreeningRole: (role: string) =>
    request<{ ok: boolean; selected_role: string; questions: ScreeningQuestion[] }>("/api/profile/screening/select-role", {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  submitScreeningAnswers: (answers: { question_id: string; question?: string; answer: string | string[] | number | boolean; category?: string; type?: string }[], target_role?: string) =>
    request<{ ok: boolean; saved_count: number; total_qa: number; qa_history: ScreeningQAItem[] }>("/api/profile/screening/answer", {
      method: "POST",
      body: JSON.stringify({ answers, target_role }),
    }),
  regenerateScreeningQuestions: (role?: string) =>
    request<{ ok: boolean; questions: ScreeningQuestion[] }>("/api/profile/screening/regenerate", {
      method: "POST",
      body: JSON.stringify({ role: role || "" }),
    }),
};

// ── Templates ─────────────────────────────────────────────
export interface ResumeTemplateItem {
  id: string;
  name: string;
  tagline: string;
  badge: string;
  badge_color: string;
  ats_score: number;
  style: string;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  layout: string;
  ideal_for: string;
  features: string[];
}

export const templatesApi = {
  list: () => request<{ templates: ResumeTemplateItem[] }>("/api/templates"),
  select: (template_id: string) =>
    request<{ ok: boolean; selected_template: string }>("/api/templates/select", {
      method: "POST",
      body: JSON.stringify({ template_id }),
    }),
  getDownloadUrl: (template_id: string) => `${API_URL}/api/templates/${template_id}/download`,
};

// ── Jobs ──────────────────────────────────────────────────
export const jobsApi = {
  list: (params?: { page?: number; limit?: number; min_score?: number; source?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.min_score) q.set("min_score", String(params.min_score));
    if (params?.source && params.source !== "all") q.set("source", params.source);
    return request<{ items: unknown[]; total: number }>(`/api/jobs?${q}`);
  },
  get: (id: string) => request(`/api/jobs/${id}`),
  apply: (id: string) => request(`/api/jobs/${id}/apply`, { method: "POST" }),
  autoApplyForm: (id: string) =>
    request<{
      ok: boolean;
      status: string;
      message: string;
      target_url: string;
      fields_filled: Array<{ field: string; value: string; type: string }>;
      submit_button_found: boolean;
      screenshot_path?: string;
      screenshot_base64?: string;
      questions_answered?: Array<{ field: string; answer: string }>;
    }>(`/api/jobs/${id}/auto-apply-form`, { method: "POST" }),
  applyVisible: (jobId: string) =>
    request<{
      ok: boolean;
      mode: string;
      message: string;
      target_url?: string;
      details?: Record<string, unknown>;
    }>(`/api/jobs/${jobId}/apply-visible`, { method: "POST" }),
  fetchNow: () => request<{ ok: boolean; message: string }>("/api/jobs/fetch-now", { method: "POST" }),
  generateResume: (jobId: string, template?: string) =>
    request<{
      ok: boolean;
      job_id: string;
      tailored_resume: Record<string, unknown>;
      generated_at: string;
      docx_path?: string;
    }>(`/api/jobs/${jobId}/generate-resume${template ? `?template=${template}` : ""}`, { method: "POST" }),
  getResume: (jobId: string) =>
    request<{
      ok: boolean;
      job_id: string;
      tailored_resume: Record<string, unknown> | null;
      generated_at?: string;
    }>(`/api/jobs/${jobId}/resume`),
  getResumeDownloadUrl: (jobId: string, template?: string) =>
    `${API_URL}/api/jobs/${jobId}/resume/download${template ? `?template=${template}` : ""}`,
  deleteResume: (jobId: string) =>
    request<{ ok: boolean; message: string; job_id: string }>(`/api/jobs/${jobId}/resume`, { method: "DELETE" }),
  crawlDelhiNcr: (options?: { concurrency?: number; restart?: boolean }) =>
    request<{ ok: boolean; message: string; status?: CrawlerStatusResponse }>("/api/jobs/crawl-delhi-ncr", {
      method: "POST",
      body: JSON.stringify(options || {}),
    }),
  getCrawlerStatus: () =>
    request<CrawlerStatusResponse>("/api/jobs/crawler-status"),
};

// ── Settings ──────────────────────────────────────────────
export const settingsApi = {
  get: () => request("/api/settings"),
  update: (data: Record<string, unknown>) =>
    request("/api/settings", { method: "PUT", body: JSON.stringify(data) }),
  testAI: () => request("/api/settings/test-ai", { method: "POST" }),
  getModelSuggestions: () =>
    request<Record<string, string[]>>("/api/settings/models"),
  testDiscord: (webhookUrl?: string) =>
    request<{ ok: boolean; webhook_sent?: boolean; dm_sent?: boolean; message?: string; error?: string }>(
      "/api/settings/test-discord",
      { method: "POST", body: JSON.stringify({ webhook_url: webhookUrl || null }) }
    ),
  getDiscordStatus: () =>
    request<{
      bot_configured: boolean;
      bot_connected: boolean;
      global_webhook_configured: boolean;
      user_webhook_configured: boolean;
      user_discord_linked: boolean;
      user_discord_id: string | null;
      user_discord_username: string | null;
    }>("/api/settings/discord-status"),
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
  allJobs: (params?: { page?: number; limit?: number; search?: string; company?: string; source?: string; is_remote?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.search) q.set("search", params.search);
    if (params?.company && params.company !== "all") q.set("company", params.company);
    if (params?.source && params.source !== "all") q.set("source", params.source);
    if (params?.is_remote !== undefined) q.set("is_remote", String(params.is_remote));
    return request<{
      items: AdminJobRecord[];
      total: number;
      page: number;
      limit: number;
      companies: string[];
      stats: {
        total_jobs: number;
        remote_jobs: number;
        active_jobs: number;
        career_jobs?: number;
        career_crawled_jobs?: number;
        linkedin_jobs?: number;
        naukri_jobs?: number;
        companies_count: number;
      };
    }>(`/api/admin/jobs?${q}`);
  },
  seedJobs: () =>
    request<{ ok: boolean; message: string; total_jobs: number }>("/api/admin/jobs/seed", { method: "POST" }),
  purgeStaticJobs: () =>
    request<{ ok: boolean; message: string; purged_count: number; remaining_jobs: number }>("/api/admin/jobs/purge-static", { method: "POST" }),
  purgeCrawledJobs: () =>
    request<{ ok: boolean; message: string; purged_count: number; remaining_jobs: number; crawled_jobs: number }>("/api/admin/jobs/purge-crawled", { method: "POST" }),
  purgeOldEntries: (days: number = 60) =>
    request<{
      ok: boolean;
      message: string;
      retention_days: number;
      jobs_removed: number;
      job_matches_removed: number;
      system_logs_removed: number;
      workflow_runs_removed: number;
      remaining_jobs: number;
    }>(`/api/admin/jobs/purge-old?days=${days}`, { method: "POST" }),
  fetchLiveJobs: (source: "all" | "career" | "career-crawled" | "linkedin" | "naukri" = "all") =>
    request<{ ok: boolean; message: string }>(`/api/admin/jobs/fetch-live?source=${source}`, { method: "POST" }),
  // Crawler Sync & Status
  startCrawler: (options?: { companies?: string[]; headless?: boolean; limit_per_company?: number; restart?: boolean; concurrency?: number }) =>
    request<{ ok: boolean; message: string }>("/api/admin/crawler/start", { method: "POST", body: JSON.stringify(options || {}) }),
  getCrawlerStatus: () =>
    request<CrawlerStatusResponse>("/api/admin/crawler/status"),
  pauseCrawler: () =>
    request<{
      ok: boolean;
      message: string;
      breakpoint?: {
        rank: number;
        company: string;
        completed_count: number;
        total_companies: number;
        jobs_discovered: number;
        jobs_saved: number;
        captchas_encountered?: number;
        next_company?: string;
      };
      status: CrawlerStatusResponse;
    }>("/api/admin/crawler/pause", { method: "POST" }),
  resetCrawlerCheckpoint: () =>
    request<{ ok: boolean; message: string }>("/api/admin/crawler/reset", { method: "POST" }),
  // System Logs
  getLogs: (params?: { page?: number; limit?: number; level?: string; category?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.level && params.level !== "all") q.set("level", params.level);
    if (params?.category && params.category !== "all") q.set("category", params.category);
    if (params?.search) q.set("search", params.search);
    return request<LogsResponse>(`/api/admin/logs?${q}`);
  },
  clearLogs: () =>
    request<{ ok: boolean; message: string; deleted_count: number }>("/api/admin/logs/clear", { method: "DELETE" }),
};

export interface CrawlerHistoryItem {
  company: string;
  status: "SUCCESS" | "NO_JOBS" | "CAPTCHA_ABORTED" | "ERROR";
  reason?: string;
  jobs_found: number;
  new_saved: number;
}

export interface CrawlerStatusResponse {
  is_running: boolean;
  is_paused?: boolean;
  current_company: string | null;
  active_companies?: string[];
  concurrency?: number;
  current_index: number;
  total_companies: number;
  percent: number;
  status_message: string;
  jobs_discovered: number;
  jobs_saved: number;
  captchas_encountered: number;
  started_at: string | null;
  finished_at: string | null;
  paused_at?: string | null;
  breakpoint?: {
    rank: number;
    company: string;
    completed_count: number;
    total_companies: number;
    jobs_discovered: number;
    jobs_saved: number;
    captchas_encountered?: number;
    next_company?: string;
  };
  history: CrawlerHistoryItem[];
  checkpoint?: {
    crawl_date?: string;
    completed_count: number;
    total_jobs_discovered: number;
    total_jobs_saved: number;
    last_updated?: string | null;
    last_rank?: number;
  };
}

export interface SystemLogRecord {
  _id: string;
  timestamp: string;
  level: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  category: "crawler" | "scraper" | "auth" | "matching" | "pipeline" | "system" | string;
  message: string;
  details?: Record<string, unknown>;
}

export interface LogsResponse {
  items: SystemLogRecord[];
  total: number;
  page: number;
  limit: number;
  stats: {
    total: number;
    errors: number;
    warnings: number;
    crawler: number;
  };
}

export interface AdminJobRecord {
  _id: string;
  title: string;
  company: string;
  location?: string;
  is_remote?: boolean;
  employment_type?: string;
  source?: string;
  source_url?: string;
  application_url?: string;
  description?: string;
  requirements?: string[];
  responsibilities?: string[];
  required_skills?: string[];
  salary_range?: { min?: number; max?: number; currency?: string };
  grade?: string;
  is_active?: boolean;
  enriched?: boolean;
  discovered_at?: string;
  posted_at?: string;
  posted_at_raw?: string;
  company_meta?: TargetCompany;
}

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

