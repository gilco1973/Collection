import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Profile, SectionOverview } from "../api/types";
import { DISMISS_TTL_MS, MAX_NUDGES, activeDismissals, computeNudges, type NudgeInput, type Translate } from "../nudges";
import { clearNudgeState, dismissNudge, readNudgeState, setNudgesEnabled, storageKey } from "../nudgeStore";

const NOW = Date.parse("2026-09-18T12:00:00Z");
const DAY = 24 * 60 * 60 * 1000;
const ago = (days: number) => new Date(NOW - days * DAY).toISOString();
const t: Translate = (key, params) => (params?.title ? `${key}[${params.title}]` : key);
const sections: SectionOverview[] = [
  { id: "onboarding", path: "onboarding", title: "Onboarding", owner: "enablement", review_every_days: 90, page_count: 2, stale_count: 0 },
  { id: "governance", path: "governance", title: "Governance", owner: "risk", review_every_days: 30, page_count: 1, stale_count: 0 },
  { id: "wiki", path: "wiki", title: "Wiki", owner: "everyone", review_every_days: 30, page_count: 4, stale_count: 0 },
];
const progress = [{ section: "onboarding", title: "Onboarding", viewed: 2, total: 2 }, { section: "governance", title: "Governance", viewed: 0, total: 1 }, { section: "wiki", title: "Wiki", viewed: 0, total: 4 }];
const visit = (daysAgo: number, count: number, title = "Page") => ({ first_at: ago(daysAgo + 1), last_at: ago(daysAgo), count, title });
const profile = (over: Partial<Profile> = {}): Profile => ({ persona: null, personas: [], viewed: {}, quizzes: [], progress: [], updated_at: ago(0), ...over });
const compute = (p: Profile, extra: Partial<NudgeInput> = {}) => computeNudges({ profile: p, sections, now: NOW, t, ...extra });
const ids = (p: Profile, extra: Partial<NudgeInput> = {}) => compute(p, extra).map((n) => n.id);
/** Everything at once: pages to resume, a page to quiz, sections never opened. */
const busy = profile({ viewed: { "old.md": visit(10, 1, "Old"), "older.md": visit(12, 1, "Older"), "read.md": visit(1, 2, "Read") }, progress });

describe("computeNudges", () => {
  it("welcomes a reader who has opened nothing, pointing at the first section", () => {
    expect(compute(profile())).toEqual([{ id: "welcome", kind: "welcome", title: "nudges.welcome[Onboarding]", body: "nudges.welcomeBody", to: "/kb/onboarding" }]);
    expect(compute(profile(), { sections: [] })).toEqual([]);
  });

  it("resumes the most recent page left 3–30 days ago after fewer than three visits", () => {
    const p = profile({ viewed: { "a.md": visit(5, 1, "A"), "b.md": visit(4, 2, "B"), "c.md": visit(1, 1, "C"), "d.md": visit(40, 1, "D"), "e.md": visit(6, 3, "E") } });
    expect(compute(p)[0]).toEqual({ id: "resume:b.md", kind: "resume", title: "nudges.resume", body: "nudges.resumeBody[B]", to: "/kb/page/b.md" });
    const none = profile({ viewed: { "c.md": visit(1, 1), "d.md": visit(40, 1), "e.md": visit(6, 3), "bad.md": { ...visit(5, 1), last_at: "not a date" } } });
    expect(compute(none).some((n) => n.kind === "resume")).toBe(false);
  });

  it("offers a quiz on the most-read page without a result, and none once every read page has one", () => {
    const p = profile({ viewed: { "a.md": visit(1, 2, "A"), "b.md": visit(1, 4, "B") } });
    expect(compute(p)).toEqual([{ id: "quiz:b.md", kind: "quiz", title: "nudges.quiz[B]", body: "nudges.quizBody", to: "/kb/page/b.md?quiz=1" }]);
    expect(ids({ ...p, quizzes: [{ path: "b.md", at: ago(0), score: 3, total: 4 }] })).toEqual(["quiz:a.md"]);
    expect(ids({ ...p, quizzes: [{ path: "a.md", at: ago(0), score: 1, total: 2 }, { path: "b.md", at: ago(0), score: 3, total: 4 }] })).toEqual([]);
    expect(ids(profile({ viewed: { "a.md": visit(1, 1) } }))).toEqual([]);
  });

  it("points at an unopened section only once another section has progress", () => {
    const started = profile({ viewed: { "onboarding/README.md": visit(1, 1) }, progress: [{ ...progress[0], viewed: 1 }, progress[1]] });
    expect(compute(started)).toEqual([{ id: "section:governance", kind: "section", title: "nudges.section[Governance]", body: "nudges.sectionBody", to: "/kb/governance" }]);
    expect(ids(profile({ viewed: { "x.md": visit(1, 1) }, progress: progress.map((s) => ({ ...s, viewed: 0 })) }))).toEqual([]);
    expect(ids(profile({ viewed: { "x.md": visit(1, 1) }, progress: [progress[0], { ...progress[1], total: 0 }] }))).toEqual([]);
    expect(ids(started, { sections: [sections[0]] })).toEqual([]); // progress for a section the catalogue no longer lists
  });

  it("keeps priority order — resume, quiz, section, welcome — one per rule, capped at two", () => {
    expect(ids(busy)).toEqual(["resume:old.md", "quiz:read.md"]);
    expect(MAX_NUDGES).toBe(2);
  });

  it("promotes the next candidate of a rule when its first is dismissed, and lets a dismissal lapse after 30 days", () => {
    expect(ids(busy, { dismissed: { "resume:old.md": ago(1) } })).toEqual(["resume:older.md", "quiz:read.md"]);
    expect(ids(busy, { dismissed: { "resume:old.md": ago(1), "resume:older.md": ago(2) } })).toEqual(["quiz:read.md", "section:governance"]);
    expect(ids(busy, { dismissed: { "resume:old.md": ago(1), "resume:older.md": ago(2), "quiz:read.md": ago(3), "section:governance": ago(4) } })).toEqual(["section:wiki"]);
    expect(ids(busy, { dismissed: { "resume:old.md": ago(31) } })).toEqual(["resume:old.md", "quiz:read.md"]);
    expect(activeDismissals({ a: ago(29), b: ago(31), c: "garbage" }, NOW)).toEqual(["a"]);
    expect(activeDismissals(undefined, NOW)).toEqual([]);
    expect(DISMISS_TTL_MS).toBe(30 * DAY);
  });

  it("never points two nudges at the same page, and never at the page the reader is on", () => {
    const p = profile({ viewed: { "same.md": visit(5, 2, "Same"), "other.md": visit(6, 2, "Other") }, progress });
    expect(ids(p)).toEqual(["resume:same.md", "quiz:other.md"]);
    expect(ids(p, { currentPath: "/kb/page/same.md" })).toEqual(["resume:other.md", "section:governance"]); // no quiz for the page being read
    expect(ids(busy, { currentPath: "/kb/governance", dismissed: { "resume:old.md": ago(1), "resume:older.md": ago(1), "quiz:read.md": ago(1) } })).toEqual(["section:wiki"]);
  });

  it("is deterministic for the same input and moves only with the clock it is given", () => {
    const p = profile({ viewed: { "a.md": visit(5, 1, "A") } });
    expect(compute(p)).toEqual(compute(p));
    expect(ids(p)).toEqual(["resume:a.md"]);
    expect(ids(p, { now: NOW - 4 * DAY })).toEqual([]);
  });
});

describe("nudgeStore", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("keys storage by a hash of the subject, not the subject itself", () => {
    expect(storageKey("u-1")).toMatch(/^kb\.nudges\.[0-9a-f]{8}$/);
    expect(storageKey("u-1")).toBe(storageKey("u-1"));
    expect(storageKey("u-1")).not.toBe(storageKey("u-2"));
    expect(storageKey("")).toMatch(/^kb\.nudges\.[0-9a-f]{8}$/);
  });

  it("round-trips dismissals and the preference through localStorage, pruning expired entries, and can forget it all", () => {
    dismissNudge("u-1", "resume:a.md", NOW - 31 * DAY);
    dismissNudge("u-1", "quiz:b.md", NOW);
    expect(Object.keys(readNudgeState("u-1").dismissed)).toEqual(["quiz:b.md"]);
    expect(JSON.parse(localStorage.getItem(storageKey("u-1"))!)).toEqual({ enabled: true, dismissed: { "quiz:b.md": new Date(NOW).toISOString() } });
    setNudgesEnabled("u-1", false);
    setNudgesEnabled("u-1", false);
    expect(readNudgeState("u-1")).toEqual({ enabled: false, dismissed: { "quiz:b.md": new Date(NOW).toISOString() } });
    expect(readNudgeState("u-2")).toEqual({ enabled: true, dismissed: {} });
    clearNudgeState("u-1");
    clearNudgeState(undefined);
    expect(localStorage.getItem(storageKey("u-1"))).toBeNull();
    expect(readNudgeState("u-1")).toEqual({ enabled: true, dismissed: {} });
  });

  it("tolerates corrupt or foreign values and a storage that refuses reads and writes", () => {
    localStorage.setItem(storageKey("u-1"), "{not json");
    expect(readNudgeState("u-1")).toEqual({ enabled: true, dismissed: {} });
    localStorage.setItem(storageKey("u-1"), JSON.stringify({ enabled: "no", dismissed: { a: 5, b: "2026-01-01T00:00:00Z" } }));
    expect(readNudgeState("u-1")).toEqual({ enabled: true, dismissed: { b: "2026-01-01T00:00:00Z" } });
    localStorage.setItem(storageKey("u-1"), JSON.stringify({ enabled: false, dismissed: "nope" }));
    expect(readNudgeState("u-1")).toEqual({ enabled: false, dismissed: {} });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readNudgeState("u-3")).toEqual({ enabled: true, dismissed: {} });
    dismissNudge("u-3", "welcome", NOW);
    expect(Object.keys(readNudgeState("u-3").dismissed)).toEqual(["welcome"]); // kept for the session even though nothing was stored
    clearNudgeState("u-3");
    expect(readNudgeState("u-3")).toEqual({ enabled: true, dismissed: {} });
  });
});
