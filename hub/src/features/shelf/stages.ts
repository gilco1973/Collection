import type { ShelfEntry, ShelfRole } from "../../api/types";

/**
 * Pure helpers behind the sign-off queue and the onboarding tracker. Everything
 * shown is read from the shelf record (the manifest's facts) and from what the
 * hub recorded this session; nothing is inferred.
 */

export const STAGE_LABELS = ["scaffolded", "built", "used once for real", "owner signed", "AI security signed", "on the shelf"] as const;

export const ROLE_LABEL: Record<ShelfRole, string> = { owner: "Owner", ai_security: "AI security" };

export type SignoffView = {
  /** signed: in the manifest at this version; recorded: through the hub, awaiting commit; stale: a previous version; pending. */
  kind: "signed" | "recorded" | "stale" | "pending";
  text: string;
  chip: "ok" | "warn" | "line" | "crit";
};

/** One line per sign-off role, as the queue and the listing show it. */
export function signoffView(e: ShelfEntry, role: ShelfRole): SignoffView {
  const s = e.signoff[role];
  if (s && s.version === e.version) return { kind: "signed", text: `${s.by} · ${s.date}`, chip: "ok" };
  const r = e.recorded[role];
  if (r) return { kind: "recorded", text: `${r.by} · ${r.date} · awaiting commit`, chip: "warn" };
  if (s) return { kind: "stale", text: `stale: signed at ${s.version} by ${s.by}`, chip: "crit" };
  return { kind: "pending", text: "pending", chip: "line" };
}

/** Roles this person may sign for on this component right now: allowed, still open, and not yet recorded here. */
export function openRolesFor(e: ShelfEntry): ShelfRole[] {
  if (e.status !== "ready") return [];
  return e.youMaySign.filter((role) => {
    const v = signoffView(e, role);
    return v.kind === "pending" || v.kind === "stale";
  });
}

export type StageGroup = { key: string; title: string; note: string; entries: ShelfEntry[] };

/** The tracker's groups, furthest along first, so the shelf reads top-down as "done, nearly, next". */
export function groupByStage(entries: ShelfEntry[]): StageGroup[] {
  const defs: Array<[string, string, string, (e: ShelfEntry) => boolean]> = [
    [
      "shelf",
      "On the shelf",
      "signed by the owner and an AI security engineer at the current version; the hub lists them as GA",
      (e) => e.stage.label === "on the shelf",
    ],
    [
      "security",
      "Awaiting AI security sign-off",
      "the owner has signed; an AI security engineer reads the rules and the walkthrough, runs the example, and signs",
      (e) => e.stage.index === 3,
    ],
    ["owner", "Awaiting owner sign-off", "used once for real; the owner signs when the tests are green", (e) => e.stage.index === 2],
    ["built", "Built, not yet used for real", "tests green; needs one real use, recorded by the owner", (e) => e.stage.index === 1],
    ["scaffolded", "Scaffolded", "a manifest and placeholders; README, walkthrough, example and tests still to fill", (e) => e.stage.index === 0],
    ["deprecated", "Deprecated", "past the shelf; consumers move to the replacement", (e) => e.status === "deprecated"],
  ];
  return defs.map(([key, title, note, test]) => ({ key, title, note, entries: entries.filter(test) })).filter((g) => g.entries.length > 0);
}

export function counts(entries: ShelfEntry[]) {
  return {
    total: entries.length,
    signed: entries.filter((e) => e.signed).length,
    awaitingOwner: entries.filter((e) => e.status === "ready" && signoffView(e, "owner").kind !== "signed").length,
    awaitingSecurity: entries.filter((e) => e.status === "ready" && signoffView(e, "ai_security").kind !== "signed").length,
    recorded: entries.reduce((n, e) => n + Object.keys(e.recorded).length, 0),
  };
}
