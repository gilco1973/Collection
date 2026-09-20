/** `GET /api/insights`: aggregates only — paths, counts and rates. Reader-derived numbers are `null` below k readers. */
export interface PageInsight {
  views: number | null;
  readers: number | null;
  problems: Record<string, number>;
  quiz_attempts: number | null;
  quiz_fail_rate: number | null;
  chat_citations: number;
}

export interface Insights {
  generated_at: string;
  k: number;
  window_days: number;
  pages: Record<string, PageInsight>;
  unanswered: { mode: Record<string, number>; lang: Record<string, number> };
  suppressed: number;
}
