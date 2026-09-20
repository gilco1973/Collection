/** Route table for the Employee AI Hub.
 *
 * Paths follow the Hub's four areas from the experience design specification
 * (§6): Discover, My workspace, Build, Learn.
 */
export const ROUTES = {
  discover: "/discover",
  listing: "/discover/agents/investigation-triage",
  assistant: "/assistant",
  workspace: "/workspace",
  intake: "/build/intake",
  learn: "/learn",
  settings: "/settings",
} as const;

export type RouteKey = keyof typeof ROUTES;

/** Plural path segment per consumer kind: /discover/agents/investigation-triage. */
export const KIND_SEGMENT: Record<string, string> = { assistant: "assistants", agent: "agents", knowledge: "knowledge", tool: "tools", road: "roads" };

/** Where opening a listing leads: assistants open a conversation, everything else its listing page. */
export function consumerRoute(c: { kind: string; slug: string; id: string }): string {
  return `/discover/${KIND_SEGMENT[c.kind] ?? "catalog"}/${c.slug}`;
}
export function assistantRoute(consumerId: string, q?: string): string {
  return `${ROUTES.assistant}/${consumerId}${q ? `?q=${encodeURIComponent(q)}` : ""}`;
}

/** Screen title shown in the browser tab and the route chooser. */
export const SCREEN_TITLES: Record<string, string> = {
  [ROUTES.discover]: "Discover",
  [ROUTES.assistant]: "Employee assistant",
  [ROUTES.workspace]: "My workspace",
  [ROUTES.intake]: "Intake brief",
  [ROUTES.learn]: "Learn",
  [ROUTES.settings]: "Settings",
};

/**
 * Clickable label -> destination.
 *
 * The artboard markup is reproduced byte-for-byte, so it carries no `href`s and
 * no handlers. Rather than edit the markup (which would break the pixel match),
 * the shell delegates clicks and resolves them by the element's own text. Keys
 * are compared case-insensitively against the trimmed text of the nearest
 * `.btn`, `.links span`, `.lc`, `.hsec .hh a` or `[data-nav]` ancestor.
 */
export const NAV_BY_LABEL: Record<string, string> = {
  // Primary navigation, present on every screen.
  discover: ROUTES.discover,
  "my workspace": ROUTES.workspace,
  build: ROUTES.intake,
  learn: ROUTES.learn,

  // Discover -> a listing, and the assistant.
  open: ROUTES.listing,
  view: ROUTES.listing,
  "read contract": ROUTES.listing,
  changelog: ROUTES.listing,
  "investigation triage": ROUTES.listing,
  "employee assistant": ROUTES.assistant,
  "policy and procedures": ROUTES.listing,

  // Anything that starts or continues a brief.
  "start a brief": ROUTES.intake,
  "start an intake brief": ROUTES.intake,
  "save draft": ROUTES.intake,
  "continue to model": ROUTES.intake,

  // Back out to the catalog.
  "browse the catalog": ROUTES.discover,
  "all updates": ROUTES.discover,
  "see the six roads": ROUTES.discover,

  // Listing actions that open a conversation with the agent.
  "open in the portal": ROUTES.assistant,
  "try in playground": ROUTES.assistant,
};
