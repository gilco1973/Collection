/**
 * What the front end knows about who is signed in.
 *
 * Two layers, on purpose. `AuthState` is the token lifecycle owned by the
 * identity provider (signed in or not, and how to get a bearer token). The
 * `Principal` is what the platform says about that person after resolving the
 * token: roles, ladder, teams, entitlements. It comes from `GET /me`, never from
 * token claims read on the client, because the platform's principal record is
 * the authority.
 */

export type Ladder = "L0" | "L1" | "L2" | "L3";
export type Channel = "operator" | "customer" | "partner" | "machine";

/** Roles the Hub understands. The server may send others; they are kept but not interpreted. */
export type Role = "employee" | "ops.investigator" | "ops.lead" | "platform.lead" | "approver" | "audit" | "admin" | (string & {});

export interface Principal {
  id: string;
  name: string;
  email: string;
  /** Two-letter initials for the avatar, computed server-side so it matches the portal. */
  initials: string;
  tenant: string;
  roles: Role[];
  /** The person's own autonomy ceiling; a consumer's ladder may be lower. */
  ladder: Ladder;
  channel: Channel;
  teams: Array<{ id: string; name: string; lead: boolean }>;
  costCentre: string;
  /** Consumer ids this person may open, resolved from role and channel by the policy bundle. */
  entitlements: string[];
  preferences: Preferences;
}

export interface Preferences {
  theme: "system" | "light" | "dark";
  /** Self-declared assistive-technology preference, carried as an entitlement on every channel. */
  accessibility: boolean;
  /** A person may decline AI assistance; routes to a person by default. */
  noAssistant: boolean;
  density: "comfortable" | "dense";
  locale: string;
  notifications: { requests: boolean; briefs: boolean; digest: boolean };
}

export type AuthStatus = "loading" | "signed-out" | "signing-in" | "signed-in" | "error";

export interface AuthSnapshot {
  status: AuthStatus;
  /** Present when signed in; refreshed silently by the provider. */
  accessToken?: string;
  /** Provider's own subject and display name, before the platform resolves the principal. */
  subject?: { id: string; name?: string; email?: string };
  error?: string;
}

/** A sign-in persona for the mock provider (dev, demos, tests). */
export interface MockPersona {
  id: string;
  label: string;
  description: string;
}
