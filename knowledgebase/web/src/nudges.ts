import type { Profile, SectionOverview } from "./api/types";

/**
 * The proactive librarian, computed in the browser. Pure: given the reader's profile and the section list
 * (both already served to the reader), a clock, the dismissals and the current route, it returns at most two
 * suggestions. Nothing here talks to the network, to React or to storage.
 */
export type NudgeKind = "resume" | "quiz" | "section" | "welcome";

export interface Nudge {
  /** Stable per subject (`resume:<path>`, `quiz:<path>`, `section:<id>`, `welcome`) so a dismissal sticks. */
  id: string;
  kind: NudgeKind;
  title: string;
  body: string;
  to: string;
}

/** A translator in the shape of i18next's `t`, injected so this module stays free of the i18n singleton. */
export type Translate = (key: string, params?: Record<string, string>) => string;

export interface NudgeInput {
  profile: Profile;
  sections: SectionOverview[];
  /** Epoch milliseconds; passed in rather than read from the clock so the result is deterministic. */
  now: number;
  /** Dismissed nudge id → ISO time of the dismissal. Entries older than `DISMISS_TTL_MS` no longer count. */
  dismissed?: Record<string, string>;
  /** The console route the reader is on (`/kb/page/<path>`, `/kb/<id>`); suggesting it would be pointless. */
  currentPath?: string;
  t: Translate;
}

export const MAX_NUDGES = 2;
const DAY_MS = 24 * 60 * 60 * 1000;
export const DISMISS_TTL_MS = 30 * DAY_MS;
export const RESUME_MIN_DAYS = 3;
export const RESUME_MAX_DAYS = 30;
/** A page opened this many times or more is considered finished, not something to resume. */
export const RESUME_MAX_VIEWS = 3;
export const QUIZ_MIN_VIEWS = 2;

const ageDays = (iso: string, now: number): number => (now - Date.parse(iso)) / DAY_MS;

/** The ids whose dismissal is still in force at `now`. */
export function activeDismissals(dismissed: Record<string, string> | undefined, now: number): string[] {
  return Object.entries(dismissed ?? {})
    .filter(([, at]) => now - Date.parse(at) < DISMISS_TTL_MS)
    .map(([id]) => id);
}

/** A rule lists every candidate it has, best first; `computeNudges` takes the first admissible one. */
type Rule = (input: NudgeInput) => Nudge[];

/** Pages left 3–30 days ago after fewer than three visits, most recently opened first. */
const resume: Rule = ({ profile, now, t }) =>
  Object.entries(profile.viewed)
    .filter(([, v]) => v.count < RESUME_MAX_VIEWS && ageDays(v.last_at, now) >= RESUME_MIN_DAYS && ageDays(v.last_at, now) <= RESUME_MAX_DAYS)
    .sort(([pa, a], [pb, b]) => b.last_at.localeCompare(a.last_at) || pa.localeCompare(pb))
    .map(([path, v]): Nudge => ({ id: `resume:${path}`, kind: "resume", title: t("nudges.resume"), body: t("nudges.resumeBody", { title: v.title }), to: `/kb/page/${path}` }));

/** Pages read at least twice with no quiz result yet; the most read first, then the most recent. */
const quiz: Rule = ({ profile, t }) => {
  const done = new Set(profile.quizzes.map((q) => q.path));
  return Object.entries(profile.viewed)
    .filter(([path, v]) => v.count >= QUIZ_MIN_VIEWS && !done.has(path))
    .sort(([pa, a], [pb, b]) => b.count - a.count || b.last_at.localeCompare(a.last_at) || pa.localeCompare(pb))
    .map(([path, v]): Nudge => ({ id: `quiz:${path}`, kind: "quiz", title: t("nudges.quiz", { title: v.title }), body: t("nudges.quizBody"), to: `/kb/page/${path}?quiz=1` }));
};

/** Sections never opened, in catalogue order, once the reader has started somewhere else. */
const section: Rule = ({ profile, sections, t }) => {
  if (!profile.progress.some((p) => p.viewed > 0)) return [];
  const progress = new Map(profile.progress.map((p) => [p.section, p]));
  return sections
    .filter((s) => (progress.get(s.id)?.viewed ?? 1) === 0 && (progress.get(s.id)?.total ?? 0) > 0)
    .map((s): Nudge => ({ id: `section:${s.id}`, kind: "section", title: t("nudges.section", { title: s.title }), body: t("nudges.sectionBody"), to: `/kb/${s.id}` }));
};

/** A reader who has opened nothing yet is pointed at the first section. */
const welcome: Rule = ({ profile, sections, t }) => {
  const first = sections[0];
  if (!first || Object.keys(profile.viewed).length > 0) return [];
  return [{ id: "welcome", kind: "welcome", title: t("nudges.welcome", { title: first.title }), body: t("nudges.welcomeBody"), to: `/kb/${first.id}` }];
};

/** Priority order: what to finish, what to test, what to discover, where to begin. One nudge per rule at most. */
const RULES: Rule[] = [resume, quiz, section, welcome];

/** The part of the id after the kind — a path or section id — so two nudges never point at the same thing. */
const subjectOf = (nudge: Nudge): string => nudge.id.slice(nudge.id.indexOf(":") + 1);
const routeOf = (nudge: Nudge): string => nudge.to.split("?")[0];

/**
 * At most `MAX_NUDGES` nudges, one per rule in priority order. Within a rule the first candidate that is not
 * dismissed, not the page the reader is on and not about a subject already chosen wins, so dismissing one
 * page promotes the next. Deterministic for the same input.
 */
export function computeNudges(input: NudgeInput): Nudge[] {
  const dismissed = new Set(activeDismissals(input.dismissed, input.now));
  const out: Nudge[] = [];
  const admissible = (n: Nudge) => !dismissed.has(n.id) && routeOf(n) !== input.currentPath && !out.some((o) => subjectOf(o) === subjectOf(n));
  for (const rule of RULES) {
    if (out.length >= MAX_NUDGES) break;
    const pick = rule(input).find(admissible);
    if (pick) out.push(pick);
  }
  return out;
}
