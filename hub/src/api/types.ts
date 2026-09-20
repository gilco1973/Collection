import type { Ladder } from "../auth/types";
import type { BriefContent, BriefStepKey } from "./schemas";

export type { Principal, Preferences, Ladder, Role, Channel } from "../auth/types";
export type { BriefContent, BriefStepKey } from "./schemas";

/* ---------- Catalog and consumers ---------- */

export type Road = "R1" | "R2" | "R3" | "R4" | "R5" | "R6";
export type ConsumerKind = "assistant" | "agent" | "knowledge" | "tool" | "road";
export type Lifecycle = "GA" | "preview" | "deprecates" | "retired";
/** How this person may reach the listing; resolved by the policy bundle, never typed by the owner (PLT-UI-17). */
export type Access = "open" | "request" | "view" | "contract";

export interface Chip {
  text: string;
  kind?: "" | "line" | "accent" | "ok" | "warn" | "crit" | "money" | "model" | "mono" | "ink";
}

export interface ConsumerSummary {
  id: string;
  slug: string;
  kind: ConsumerKind;
  name: string;
  description: string;
  road: Road;
  lifecycle: Lifecycle;
  /** Icon tint on the card: a accent, w warn, m model, p money, or none. */
  icon: "a" | "w" | "m" | "p" | "";
  /** Which glyph the card draws (see `ui/icons.tsx`). */
  glyph: "sparkle" | "pulse" | "book" | "pen" | "chat" | "bolt" | "shield" | "layers";
  /** For `access: "request"`: whether the person asks for access or for a role. */
  requestKind?: "access" | "role";
  /** A few words for pickers, e.g. "policies, procedures, your cases". */
  tagline?: string;
  /** Chips exactly as the listing shows them, derived server-side from the system record. */
  meta: Chip[];
  /** One line of adoption or ownership shown in the card foot. */
  footNote: string;
  access: Access;
  /** Listed from the components collection: shown under its kind's tab, in search and on its page, not in the artboard's default "All" tab. */
  collection?: boolean;
}

export interface Tile {
  label: string;
  value: string;
  small?: string;
  note: string;
}
export interface CatalogEntry {
  op: string;
  tier: "R" | "W1" | "W2" | "M" | "R5";
  classes: string;
  note: string;
}
export interface GetStartedStep {
  n: string;
  title: string;
  small: string;
  state: "done" | "on" | "";
}
export interface VersionRow {
  version: string;
  state: "current" | "supported" | "retired";
  date: string;
}

export interface ConsumerDetail extends ConsumerSummary {
  crumbs: string[];
  /** Ladder the signed-in person acts at on this consumer (the lower of theirs and the consumer's). */
  youActAt: Ladder;
  ladderMax: Ladder;
  /** Chips in the header row, e.g. road R2, profile read, audience internal, GA since Phase 1. */
  headerChips: Chip[];
  tiles: Tile[];
  does: string[];
  catalog: { name: string; signed: boolean; entries: CatalogEntry[] };
  trust: Tile[];
  evidence: Array<{ label: string; href: string; icon: "doc" | "db" | "shield" | "pulse" }>;
  cost: Array<{ label: string; value: string; note: string }>;
  getStarted: GetStartedStep[];
  owner: Array<{ label: string; value: string }>;
  versions: VersionRow[];
  /** Where the full changelog lives (catalog record); the listing shows the last three versions. */
  changelogHref: string;
}

export interface ChangeRow {
  date: string;
  kind: Chip;
  text: string;
}

export interface Catalog {
  /** "4 services available to you" */
  availableCount: number;
  available: ConsumerSummary[];
  listings: ConsumerSummary[];
  counts: Record<"all" | "assistants" | "agents" | "knowledge" | "tools" | "roads", number>;
  changes: ChangeRow[];
  suggestions: string[];
}

/* ---------- The shelf: components of the collection, their sign-offs and onboarding stage ---------- */

export type ShelfRole = "owner" | "ai_security";
export type ShelfCategory = "agent" | "harness" | "tool" | "integration" | "pattern" | "skill";
/** A sign-off as the manifest records it: who, when, at which version. Null while pending. */
export type ShelfSignoff = { by: string; date: string; version: string } | null;

/** One component as `tools/shelf.py --write` exports it from its manifest: facts, never guesses. */
export interface ShelfRecord {
  name: string;
  title: string;
  version: string;
  /** The category of AI component: an agent (template, tools, harness), the harness itself, a tool, an integration, a pattern, or a skill anyone can follow. */
  category: ShelfCategory;
  language: string;
  owner: string;
  status: "ready" | "draft" | "deprecated";
  summary: string;
  signoff: Record<ShelfRole, ShelfSignoff>;
  /** Both sign-offs name the current version. */
  signed: boolean;
  /** "signed", or which sign-offs are pending or stale. */
  state: string;
  /** Projects the component has been used in for real; the owner signs only after one is recorded. */
  usedIn: string[];
  /** Where it is in the onboarding process (CONTRIBUTING.md): 0 scaffolded … 5 on the shelf; `of` past the end means deprecated. */
  stage: { index: number; of: number; label: string; next: string };
  gates: { readme: boolean; walkthrough: boolean; example: boolean; tests: boolean; spec: boolean };
  test: string;
  exampleRun: string;
  hubPath: string;
  repoPath: string;
}

/** What a signer attests to on the form; every box must be ticked, the server refuses otherwise. */
export interface ShelfAttestation {
  testsGreen: boolean;
  exampleRun: boolean;
  walkthroughRead: boolean;
  rulesRead: boolean;
}

/** A sign-off recorded through the hub, before it is applied to the manifest and committed. */
export interface ShelfSignoffRecord {
  id: string;
  component: string;
  role: ShelfRole;
  by: string;
  email: string;
  date: string;
  version: string;
  usedIn?: string;
  note?: string;
  attest: ShelfAttestation;
  recordedAt: string;
}

/** A shelf record with what this session has recorded on top of the manifest. */
export interface ShelfEntry extends ShelfRecord {
  recorded: Partial<Record<ShelfRole, ShelfSignoffRecord>>;
  /** Roles the signed-in person may sign for on this component (owner by name, AI security by role). */
  youMaySign: ShelfRole[];
}

/** The file the queue exports; `python3 tools/shelf.py --apply-signoffs <file>` writes it into the manifests. */
export interface ShelfExport {
  generatedAt: string;
  apply: string;
  signoffs: ShelfSignoffRecord[];
}

/* ---------- Registry (systems of record and tools a brief may name) ---------- */

export interface RegistrySystem {
  id: string;
  name: string;
  owner: string;
  /** A system without a recorded contract cannot be named by a first consumer (PLT-ONB-6). */
  contract: "recorded" | "missing";
}

export interface RegistryTool {
  name: string;
  systemId: string;
  tier: Tier;
  classes: DataClass[];
  description: string;
}

/* ---------- Briefs (intake) ---------- */

export type BriefStatus = "draft" | "filed" | "in_review" | "needs_info" | "registered" | "merged" | "out_of_scope" | "declined";

export interface Brief {
  id: string;
  status: BriefStatus;
  /** Optimistic-concurrency token; sent back as If-Match on every write. */
  etag: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  currentStep: BriefStepKey;
  /** Steps the person has completed at least once. */
  completed: BriefStepKey[];
  content: BriefContent;
  /** Set on file: the road the lead confirmed and the outcome reason, if any. */
  road?: Road;
  outcomeReason?: string;
}

export interface BriefEstimate {
  modelSpendMonthly: number;
  modelSpendBasis: string;
  reviewHours: number;
  reviewNote: string;
  platformShare: string;
  basis: string;
}

export interface RoadRecommendation {
  road: Road;
  title: string;
  subtitle: string;
  selfService: boolean;
  note: string;
  next: Array<{ week: string; title: string; small: string }>;
}

/* ---------- Requests (access, ladder, role) ---------- */

export type RequestKind = "access" | "ladder" | "role";
export type RequestStatus = "pending" | "granted" | "denied";

export interface AccessRequest {
  id: string;
  kind: RequestKind;
  consumerId?: string;
  title: string;
  note: string;
  status: RequestStatus;
  createdAt: string;
}

/* ---------- Workspace ---------- */

export type OnboardingStep = 1 | 2 | 3 | 4 | 5 | 6 | 7;

export interface TeamConsumer {
  id: string;
  name: string;
  status: Chip;
  step: OnboardingStep;
  stepNote: string;
  /** Pipe cells: done, on, or pending, seven in all. */
  pipe: Array<"done" | "on" | "">;
  note: string;
  briefId?: string;
}

export interface Workspace {
  header: { name: string; role: string; team: string; costCentre: string };
  assistants: Array<{ consumerId: string; name: string; sub: string; lifecycle: Lifecycle; ai: boolean }>;
  teamConsumers: TeamConsumer[];
  requests: AccessRequest[];
  usage: { sandboxMonth: string; sandboxNote: string; productionNote: string; playgroundToday: string; playgroundBudget: string; playgroundPct: number };
  playground: { gateway: string; keyMasked: string; fixtures: string; example: string };
}

/* ---------- Assistant: conversations and the view-descriptor stream ---------- */

export interface ConversationSummary {
  id: string;
  title: string;
  when: string;
  via?: string;
  assistantId: string;
}

export type Provenance = "model" | "system" | "upstream";
export type ToolCallState = "proposed" | "running" | "allowed" | "denied" | "pending";
export type Tier = "R" | "W1" | "W2" | "M";
export type DataClass = "internal" | "confidential" | "restricted";

/**
 * The closed, versioned descriptor set of specification §8.2. Services and the
 * harness emit these; the modules render them. Text from a model is always a
 * `text` leaf with provenance, never markup.
 */
export type View =
  | { kind: "text"; text: string; provenance: Provenance; claims?: Array<{ span: [number, number]; support: "cited" | "tool" | "unsupported"; ref?: string }> }
  | {
      kind: "tool_call";
      tool: string;
      state: ToolCallState;
      tier: Tier;
      args_summary: Array<{ label: string; value: string }>;
      deny_code?: string;
      ms?: number;
    }
  | { kind: "citation"; source: string; chunk_ref: string; classification: "internal" | "confidential" | "restricted" }
  | { kind: "form"; schema: Record<string, unknown>; ttl_s?: number; request_hash?: string }
  | { kind: "stop"; reason: string; message: string }
  | { kind: "budget"; tokens: [number, number]; tool_calls: [number, number]; time_s: [number, number] }
  | { kind: "feedback"; seq: number; question: string }
  | { kind: "handoff"; route: "human" | "callback" | "secure_message"; expected_wait_s?: number; reason?: string }
  | { kind: "interrupt"; turn: number };

export interface TurnEvent {
  seq: number;
  view: View;
}

export interface Turn {
  id: string;
  role: "user" | "assistant";
  at: string;
  /** For assistant turns: the descriptor stream, in order. For user turns: one text view. */
  views: View[];
  sourcesLabel?: string;
  sources?: Chip[];
}

export interface Conversation {
  id: string;
  title: string;
  assistantId: string;
  assistant: { name: string; sub: string; chips: Chip[] };
  turns: Turn[];
}
