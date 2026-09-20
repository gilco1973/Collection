import type { ChatContext, ChatMode } from "./chatTypes";
import type { Insights } from "./insightsTypes";
import type { AuditDetailData, AuditSummary, ChatResponse, ChatTurnBody, Contract, Finding, LibrarianAction, Me, PageDetail, PageSummary, Profile, QuizResult, SearchResult, SectionOverview, StartAuditBody } from "./types";

const KEY_STORAGE = "kb.apiKey";
export const API_BASE = (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "");

export function readApiKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function storeApiKey(key: string): void {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable */
  }
}

/** Percent-encode each segment of a docs-relative path, keeping the slashes. */
export const encodePath = (path: string): string => path.split("/").map(encodeURIComponent).join("/");
export const fileUrl = (path: string): string => `${API_BASE}/files/${encodePath(path)}`;

export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  const key = readApiKey();
  if (key) headers.Authorization = `Bearer ${key}`;
  if (init.body) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    let message = response.statusText || `HTTP ${response.status}`;
    let requestId: string | undefined;
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
      requestId = body?.error?.request_id;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message, requestId);
  }
  return (await response.json()) as T;
}

const query = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) search.set(k, v);
  const text = search.toString();
  return text ? `?${text}` : "";
};

/** Where a browser goes to sign in; `next` is a same-origin path the API validates before redirecting back. */
export const signInUrl = (next: string): string => `${API_BASE}/auth/login?next=${encodeURIComponent(next)}`;

export const api = {
  me: () => request<Me>("/me"),
  signOut: () => request<void>("/auth/logout", { method: "POST" }),
  signOutEverywhere: () => request<void>("/auth/logout-everywhere", { method: "POST" }),
  profile: () => request<Profile>("/profile"),
  recordView: (path: string) => request<{ path: string; count: number }>("/profile/views", { method: "POST", body: JSON.stringify({ path }) }),
  setPersona: (persona: string | null) => request<Profile>("/profile/persona", { method: "PUT", body: JSON.stringify({ persona }) }),
  forgetMe: () => request<void>("/profile", { method: "DELETE" }),
  contract: () => request<Contract>("/contract"),
  sections: (lang?: string) => request<SectionOverview[]>(`/sections${query({ lang })}`),
  sectionPages: (id: string, lang?: string) => request<{ items: PageSummary[] }>(`/sections/${encodeURIComponent(id)}/pages${query({ lang })}`),
  pages: (params: { owner?: string; stale?: string; audience?: string; lang?: string }) => request<{ items: PageSummary[] }>(`/pages${query(params)}`),
  page: (path: string, lang?: string) => request<PageDetail>(`/pages/${encodePath(path)}${query({ lang })}`),
  pageFindings: (path: string) => request<{ items: Finding[] }>(`/pages/${encodePath(path)}/findings`),
  reportProblem: (path: string, body: { category: string; message: string }) =>
    request<{ id: string; owner: string | null }>(`/pages/${encodePath(path)}/reports`, { method: "POST", body: JSON.stringify(body) }),
  search: (params: Record<string, string | undefined>) => request<SearchResult>(`/search${query(params)}`),
  audits: (params: Record<string, string | undefined> = {}) => request<{ items: AuditSummary[]; total: number }>(`/audits${query(params)}`),
  audit: (id: string) => request<AuditDetailData>(`/audits/${encodeURIComponent(id)}`),
  startAudit: (body: StartAuditBody) =>
    request<{ audit_id: string; dry_run: boolean; forced_dry_run: boolean }>("/audits", { method: "POST", body: JSON.stringify(body) }),
  cancelAudit: (id: string) => request<{ status: string }>(`/audits/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  rollback: (id: string, actionId: string, body: { reason: string; force: boolean }) =>
    request<{ action: LibrarianAction }>(`/audits/${encodeURIComponent(id)}/actions/${encodeURIComponent(actionId)}/rollback`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  exportUrl: (id: string, format: "json" | "md") => `${API_BASE}/audits/${encodeURIComponent(id)}/export?format=${format}`,
  chat: (body: { message: string; history: ChatTurnBody[]; lang?: string; mode?: ChatMode; context?: ChatContext }) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(body) }),
  recordQuiz: (body: { path: string; score: number; total: number }) =>
    request<QuizResult>("/profile/quizzes", { method: "POST", body: JSON.stringify(body) }),
  insights: () => request<Insights>("/insights"),
  refreshInsights: () => request<Insights>("/insights/refresh", { method: "POST" }),
};
