import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import Layout from "../components/Layout";
import type { AuditDetailData, AuditSummary, Contract, Me, PageDetail, PageSummary, Profile, SectionOverview } from "../api/types";

export const me: Me = { role: "operator", live_allowed: true, atlassian_configured: false, sso_configured: false, user: null, operator_via: "key" };
export const viewer: Me = { role: "viewer", live_allowed: false, atlassian_configured: false, sso_configured: false, user: null, operator_via: null };
export const signedIn: Me = { ...viewer, sso_configured: true, user: { sub: "u-1", name: "Ada Lovelace", email: "ada@example.com", operator: false } };
export const profile: Profile = {
  persona: null, personas: ["new-hire", "engineer"], quizzes: [], updated_at: "2026-09-18T10:00:00Z",
  viewed: { "onboarding/README.md": { first_at: "2026-09-17T10:00:00Z", last_at: "2026-09-18T09:00:00Z", count: 2, title: "Onboarding" } },
  progress: [{ section: "onboarding", title: "Onboarding", viewed: 1, total: 2 }, { section: "governance", title: "Governance", viewed: 0, total: 1 }],
};
export const sections: SectionOverview[] = [
  { id: "onboarding", path: "onboarding", title: "Onboarding", owner: "enablement", review_every_days: 90, page_count: 2, stale_count: 1 },
  { id: "governance", path: "governance", title: "Governance", owner: "risk", review_every_days: 30, page_count: 1, stale_count: 0 },
];
export const page = (over: Partial<PageSummary> = {}): PageSummary => ({
  path: "onboarding/README.md", title: "Onboarding", section: "onboarding", owner: "enablement", status: "active", reviewed: "2026-09-01",
  next_review: "2026-11-30", stale: false, tags: ["onboarding"], audience: ["new-hire"], frontmatter_error: null, ...over,
});
export const detail: PageDetail = { meta: page(), body_markdown: "# Onboarding\n\nHello [governance](../governance/README.md) and `code`.\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nx\n```\n", withheld: false, section: { id: "onboarding", title: "Onboarding" }, translated: false };
export const summary = (over: Partial<AuditSummary> = {}): AuditSummary => ({
  audit_id: "audit-1", audit_type: "agent", status: "completed", dry_run: true, issues_found: 2, by_severity: { error: 2 }, fixes_applied: 0,
  fixes_proposed: 1, manual_review_needed: 1, tool_calls: 3, denied_calls: 1, total_cost_usd: 0.12, num_turns: 4, audit_date: "2026-09-15T10:00:00Z",
  completed_at: "2026-09-15T10:01:00Z", capabilities: ["links"], error: null, reason: null, requested_by: null, ...over,
});
export const audit = (over: Partial<AuditDetailData> = {}): AuditDetailData => ({
  audit_id: "audit-1", audit_type: "agent", status: "completed", dry_run: false, capabilities: ["links"],
  findings: [{ check: "links", severity: "error", path: "onboarding/stale.md", message: "broken link", fix_hint: "fix it", auto_fixable: false, line: 11 }],
  fixes_applied: [
    { action_id: "act-1", action_type: "set_frontmatter_field", path: "onboarding/stale.md", description: "status", dry_run: false, rolled_back: false, rollback_timestamp: null, rollback_reason: null, rollback_forced: false, timestamp: "2026-09-15T10:00:00Z" },
    { action_id: "act-2", action_type: "regenerate_index", path: "index.md", description: "index", dry_run: true, rolled_back: false, rollback_timestamp: null, rollback_reason: null, rollback_forced: false, timestamp: "2026-09-15T10:00:00Z" },
  ],
  manual_review_needed: [{ path: "onboarding/stale.md", reason: "owner must review", severity: "warning", at: "2026-09-15T10:00:00Z" }],
  tool_calls: [
    { tool: "run_checks", input: {}, ok: true, summary: "[]", at: "2026-09-15T10:00:00Z" },
    { tool: "add_frontmatter", input: { path: "x" }, ok: false, summary: "denied: dry run", at: "2026-09-15T10:00:00Z" },
    { tool: "get_document", input: {}, ok: false, summary: "failed: boom", at: "2026-09-15T10:00:00Z" },
  ],
  ai_summary: "# Done\n\nAll good.", error: null, reason: null, requested_by: null, summary: summary({ dry_run: false }), ...over,
});
export const contract: Contract = {
  sections, capabilities: ["frontmatter", "links", "structure"], defaults: { max_turns: 40, max_budget_usd: 2 },
  frontmatter: { required: ["title"], status_values: ["draft", "active"], audience_values: ["everyone"] }, taxonomy: { tags: ["onboarding"] },
  catalogs: [{ path: "onboarding/catalog.yaml" }], i18n: { languages: ["es", "he"] },
};

export type Responder = (path: string, init?: RequestInit) => unknown;

export function mockFetch(responder: Responder) {
  const calls: { path: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/^\/api/, "");
    calls.push({ path, init });
    const body = responder(path, init);
    if (body instanceof Response) return body.clone(); // a body can be read once; refetches need a fresh copy
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export const errorResponse = (status: number, message: string) =>
  new Response(JSON.stringify({ error: { code: "http_error", message, request_id: "req-1" } }), { status, headers: { "Content-Type": "application/json" } });

export function defaultResponder(overrides: Record<string, unknown> = {}): Responder {
  return (path) => {
    const key = Object.keys(overrides).find((k) => path === k || path.startsWith(`${k}?`));
    if (key) return overrides[key];
    if (path === "/me") return me;
    if (path === "/contract") return contract;
    if (path === "/sections" || path.startsWith("/sections?")) return sections;
    if (path.startsWith("/sections/onboarding/pages")) return { items: [page(), page({ path: "onboarding/stale.md", title: "Stale", stale: true })] };
    if (path.startsWith("/pages?")) return { items: [page({ path: "onboarding/stale.md", title: "Stale", stale: true })] };
    if (path.endsWith("/findings")) return { items: audit().findings };
    if (path.startsWith("/pages/")) return detail;
    if (path.startsWith("/search")) return { items: [{ ...page(), snippet: "hello" }], total: 1, facets: { section: [{ value: "onboarding", count: 1 }], status: [], audience: [], owner: [] } };
    if (path === "/audits" || path.startsWith("/audits?")) return { items: [summary()], total: 1 };
    if (path.startsWith("/audits/audit-1")) return audit();
    return errorResponse(404, `no route ${path}`);
  };
}

type Entry = string | { pathname: string; search?: string; state?: unknown };

export function renderAt(path: Entry, element: React.ReactNode, extraRoutes?: React.ReactNode, pattern = "*") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path={pattern} element={element} />
            {extraRoutes}
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
