import type { Principal } from "./types";

const prefs: Principal["preferences"] = { theme: "system", accessibility: false, noAssistant: false, density: "comfortable", locale: "en", notifications: { requests: true, briefs: true, digest: false } };

/** Test principals keyed by mock persona id. */
export const PRINCIPALS: Record<string, Principal> = {
  gk: { id: "gk", name: "Gil K.", email: "gk@example.test", initials: "GK", tenant: "t", roles: ["ops.lead"], ladder: "L2", channel: "operator", teams: [{ id: "team-payments-ops", name: "Payments ops", lead: true }], costCentre: "cc1", entitlements: ["investigation-triage", "employee-assistant"], preferences: prefs },
  investigator: { id: "investigator", name: "Ana P.", email: "ana@example.test", initials: "AP", tenant: "t", roles: ["ops.investigator"], ladder: "L1", channel: "operator", teams: [{ id: "team-payments-ops", name: "Payments ops", lead: false }], costCentre: "cc1", entitlements: ["investigation-triage"], preferences: prefs },
  employee: { id: "employee", name: "Sam O.", email: "sam@example.test", initials: "SO", tenant: "t", roles: [], ladder: "L0", channel: "operator", teams: [], costCentre: "cc2", entitlements: ["employee-assistant"], preferences: prefs },
};
