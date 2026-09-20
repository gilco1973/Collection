export type Severity = "critical" | "error" | "warning" | "info";
export type AuditStatus = "in_progress" | "completed" | "failed" | "cancelled";
export interface SignedInUser {
  sub: string;
  name: string;
  email: string | null;
  operator: boolean;
}

export interface PageVisit {
  first_at: string;
  last_at: string;
  count: number;
  title: string;
}

export interface SectionProgress {
  section: string;
  title: string;
  viewed: number;
  total: number;
}

export interface QuizResult {
  path: string;
  at: string;
  score: number;
  total: number;
}

export interface Profile {
  persona: string | null;
  personas: string[];
  viewed: Record<string, PageVisit>;
  quizzes: QuizResult[];
  progress: SectionProgress[];
  updated_at: string;
}

export interface Me {
  role: "viewer" | "operator";
  live_allowed: boolean;
  atlassian_configured: boolean;
  sso_configured: boolean;
  user: SignedInUser | null;
  operator_via: "key" | "group" | null;
}

export interface SectionOverview {
  id: string;
  path: string;
  title: string;
  owner: string;
  review_every_days: number;
  page_count: number;
  stale_count: number;
}

export interface PageSummary {
  path: string;
  title: string;
  section: string | null;
  owner: string | null;
  status: string | null;
  reviewed: string;
  next_review: string | null;
  stale: boolean;
  tags: string[];
  audience: string[];
  frontmatter_error: string | null;
  snippet?: string;
}

export interface PageDetail {
  meta: PageSummary;
  body_markdown: string | null;
  withheld: boolean;
  section: { id: string; title: string } | null;
  translated: boolean;
}

export interface Finding {
  check: string;
  severity: Severity;
  path: string;
  message: string;
  fix_hint: string | null;
  auto_fixable: boolean;
  line: number | null;
  details?: Record<string, string>;
}

export interface SearchResult {
  items: PageSummary[];
  total: number;
  facets: Record<string, { value: string; count: number }[]>;
}

export interface AuditSummary {
  audit_id: string;
  audit_type: "offline" | "agent";
  status: AuditStatus;
  dry_run: boolean;
  issues_found: number;
  by_severity: Record<string, number>;
  fixes_applied: number;
  fixes_proposed: number;
  manual_review_needed: number;
  tool_calls: number;
  denied_calls: number;
  total_cost_usd: number;
  num_turns: number;
  audit_date: string;
  completed_at: string | null;
  capabilities: string[];
  error: string | null;
  reason: string | null;
  requested_by: string | null;
}

export interface LibrarianAction {
  action_id: string;
  action_type: string;
  path: string;
  description: string;
  dry_run: boolean;
  rolled_back: boolean;
  rollback_timestamp: string | null;
  rollback_reason: string | null;
  rollback_forced: boolean;
  timestamp: string;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  ok: boolean;
  summary: string;
  at: string;
}

export interface ReviewItem {
  path: string;
  reason: string;
  severity: string;
  at: string;
}

export interface AuditDetailData {
  audit_id: string;
  audit_type: "offline" | "agent";
  status: AuditStatus;
  dry_run: boolean;
  capabilities: string[];
  findings: Finding[];
  fixes_applied: LibrarianAction[];
  manual_review_needed: ReviewItem[];
  tool_calls: ToolCall[];
  ai_summary: string | null;
  error: string | null;
  reason: string | null;
  requested_by: string | null;
  summary: AuditSummary;
}

export interface Contract {
  sections: SectionOverview[];
  capabilities: string[];
  defaults: { max_turns: number; max_budget_usd: number };
  frontmatter: { required: string[]; status_values: string[]; audience_values: string[] };
  taxonomy: { tags: string[] };
  catalogs: { path: string }[];
  i18n: { languages: string[] };
}

export interface StartAuditBody {
  type: "agent" | "offline";
  dry_run: boolean;
  capabilities?: string[];
  max_turns?: number;
  max_budget_usd?: number;
  network?: boolean;
  reason?: string;
}

export interface ChatTurnBody {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSource {
  path: string;
  title: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  quiz?: import("./chatTypes").QuizQuestion[]; // inline: keeps this file's import list (and length) unchanged
}
