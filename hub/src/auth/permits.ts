import type { Ladder, Principal } from "./types";

/**
 * Front-end authorization.
 *
 * This decides what to *show* and what to *attempt*. The platform's policy
 * engine decides what *happens*; a front-end check is never the control, only
 * the courtesy of not advertising what the API will refuse (the Hub's
 * "advertise nothing they cannot reach" rule, spec §8.6 and PLT-UI-17).
 *
 * The action set is closed. Adding a route means reusing an action, not
 * inventing a new one on the way past. `shelf.sign` is the one exception made
 * deliberately: signing a component is a new capability, not a route.
 */
export type Action =
  | "hub.discover"
  | "hub.workspace"
  | "assistant.use"
  | "consumer.open"
  | "consumer.request_access"
  | "consumer.request_ladder"
  | "brief.create"
  | "brief.file"
  | "brief.triage"
  | "settings.manage"
  | "admin.manage"
  | "shelf.sign";

export const LADDER_ORDER: Ladder[] = ["L0", "L1", "L2", "L3"];

export function ladderIndex(l: Ladder): number {
  return LADDER_ORDER.indexOf(l);
}

/** Role -> actions granted outright. Everything else is decided per resource below. */
const GRANTS: Record<string, Action[]> = {
  employee: ["hub.discover", "hub.workspace", "assistant.use", "consumer.request_access", "brief.create", "settings.manage"],
  "ops.investigator": ["consumer.request_ladder"],
  "ops.lead": ["consumer.request_ladder", "brief.file", "brief.triage"],
  "platform.lead": ["brief.file", "brief.triage"],
  admin: ["admin.manage", "brief.file", "brief.triage"],
  /** The AI security engineers: the role the security team lead grants on the platform principal. */
  "ai.security": ["shelf.sign"],
};

export interface Resource {
  /** For consumer.* actions: the consumer id and, for ladder requests, the ladder asked for. */
  consumerId?: string;
  ladder?: Ladder;
  /** For brief.* actions: whether the person owns the draft. */
  ownedByMe?: boolean;
  /** For shelf.sign: which sign-off, and the component's owner as its manifest names them. */
  signoffRole?: "owner" | "ai_security";
  owner?: string;
}

/** The manifest names an owner the way the platform names people: the local part of their address. */
export function ownerHandle(principal: Principal): string {
  return principal.email.split("@")[0].toLowerCase();
}

export function permits(principal: Principal | undefined, action: Action, resource: Resource = {}): boolean {
  if (!principal) return false;
  const roles = new Set<string>(["employee", ...principal.roles]);
  const granted = [...roles].some((r) => GRANTS[r]?.includes(action));

  switch (action) {
    case "consumer.open":
      // Opening is by entitlement, resolved by the policy bundle, not by role.
      return resource.consumerId ? principal.entitlements.includes(resource.consumerId) : false;
    case "consumer.request_access":
      return granted && !!resource.consumerId && !principal.entitlements.includes(resource.consumerId);
    case "consumer.request_ladder":
      // You may ask for a ladder above where you act, up to your own ceiling.
      return granted && !!resource.ladder && ladderIndex(resource.ladder) <= ladderIndex(principal.ladder);
    case "brief.file":
      // A lead files anyone's brief on their team; an author needs the lead for write profiles.
      return granted || resource.ownedByMe === true;
    case "shelf.sign":
      // The owner signs by name (the manifest's owner is their handle); AI security signs by role.
      if (resource.signoffRole === "owner") return !!resource.owner && resource.owner.toLowerCase() === ownerHandle(principal);
      if (resource.signoffRole === "ai_security") return granted;
      return false;
    default:
      return granted;
  }
}

/** Role label shown in the workspace header, e.g. `ops.lead`. */
export function primaryRole(principal: Principal): string {
  const order = ["admin", "platform.lead", "ai.security", "ops.lead", "ops.investigator", "approver", "audit"];
  return order.find((r) => principal.roles.includes(r)) ?? principal.roles[0] ?? "employee";
}

export function isTeamLead(principal: Principal, teamId?: string): boolean {
  return principal.teams.some((t) => t.lead && (!teamId || t.id === teamId));
}
