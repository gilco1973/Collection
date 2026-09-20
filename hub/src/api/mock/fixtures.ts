import type { Principal } from "../../auth/types";
import type {
  Brief,
  BriefEstimate,
  Catalog,
  ConsumerDetail,
  ConsumerSummary,
  Conversation,
  ConversationSummary,
  RegistrySystem,
  RegistryTool,
  RoadRecommendation,
  Workspace,
} from "../types";

/**
 * Illustrative data, transcribed from the design-canvas artboards so that a
 * signed-in `gk` persona renders every screen exactly as designed. Nothing
 * here is a real person, account or case.
 */

export const PRINCIPALS: Record<string, Principal> = {
  gk: {
    id: "u_gk",
    name: "Gil Klainert",
    email: "gil.klainert@crossriver.example",
    initials: "GK",
    tenant: "t_crossriver",
    roles: ["ops.lead", "ops.investigator"],
    ladder: "L2",
    channel: "operator",
    teams: [{ id: "team-payments-ops", name: "Payments operations", lead: true }],
    costCentre: "4410",
    entitlements: ["employee-assistant", "investigation-triage", "policy-and-procedures"],
    preferences: {
      theme: "system",
      accessibility: false,
      noAssistant: false,
      density: "comfortable",
      locale: "en-US",
      notifications: { requests: true, briefs: true, digest: false },
    },
  },
  investigator: {
    id: "u_ap",
    name: "Ana Petrov",
    email: "ana.petrov@crossriver.example",
    initials: "AP",
    tenant: "t_crossriver",
    roles: ["ops.investigator"],
    ladder: "L1",
    channel: "operator",
    teams: [{ id: "team-payments-ops", name: "Payments operations", lead: false }],
    costCentre: "4410",
    entitlements: ["employee-assistant", "investigation-triage", "policy-and-procedures"],
    preferences: {
      theme: "system",
      accessibility: false,
      noAssistant: false,
      density: "comfortable",
      locale: "en-US",
      notifications: { requests: true, briefs: false, digest: true },
    },
  },
  employee: {
    id: "u_so",
    name: "Sam Okafor",
    email: "sam.okafor@crossriver.example",
    initials: "SO",
    tenant: "t_crossriver",
    roles: [],
    ladder: "L0",
    channel: "operator",
    teams: [],
    costCentre: "3120",
    entitlements: ["employee-assistant", "policy-and-procedures"],
    preferences: {
      theme: "system",
      accessibility: true,
      noAssistant: false,
      density: "comfortable",
      locale: "en-US",
      notifications: { requests: true, briefs: false, digest: false },
    },
  },
  platform: {
    id: "u_dr",
    name: "Dana Ruiz",
    email: "dana.ruiz@crossriver.example",
    initials: "DR",
    tenant: "t_crossriver",
    roles: ["platform.lead"],
    ladder: "L2",
    channel: "operator",
    teams: [{ id: "platform", name: "Platform", lead: true }],
    costCentre: "1001",
    entitlements: [
      "employee-assistant",
      "investigation-triage",
      "policy-and-procedures",
      "compliance-narration",
      "payments-exception-agent",
      "online-banking-assistant",
    ],
    preferences: {
      theme: "system",
      accessibility: false,
      noAssistant: false,
      density: "dense",
      locale: "en-US",
      notifications: { requests: true, briefs: true, digest: true },
    },
  },
  security: {
    id: "u_mc",
    name: "Maya Chen",
    email: "maya.chen@crossriver.example",
    initials: "MC",
    tenant: "t_crossriver",
    roles: ["ai.security"],
    ladder: "L1",
    channel: "operator",
    teams: [{ id: "security", name: "Security", lead: false }],
    costCentre: "1002",
    entitlements: ["employee-assistant", "policy-and-procedures"],
    preferences: {
      theme: "system",
      accessibility: false,
      noAssistant: false,
      density: "dense",
      locale: "en-US",
      notifications: { requests: true, briefs: false, digest: true },
    },
  },
};

import { COLLECTION_DETAILS, COLLECTION_LISTINGS, COLLECTION_SHELF } from "./collection";
import type { ShelfRecord } from "../types";

/** The shelf as the sign-off queue and the onboarding tracker read it; generated from the manifests. */
export const SHELF: ShelfRecord[] = COLLECTION_SHELF;

export const LISTINGS: ConsumerSummary[] = [
  {
    id: "employee-assistant",
    slug: "employee-assistant",
    kind: "assistant",
    name: "Employee assistant",
    description: "Ask about policies, procedures and your own cases. Reads what your role can read; never writes.",
    road: "R2",
    lifecycle: "GA",
    icon: "a",
    glyph: "sparkle",
    meta: [
      { text: "R2 · read", kind: "" },
      { text: "internal", kind: "line" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "1,180 weekly users",
    access: "open",
    tagline: "policies, procedures, your cases",
  },
  {
    id: "investigation-triage",
    slug: "investigation-triage",
    kind: "agent",
    name: "Investigation triage",
    description: "Triages payment returns and case notes; proposes fee reversals for your confirmation.",
    road: "R2",
    lifecycle: "GA",
    icon: "w",
    glyph: "pulse",
    meta: [
      { text: "R2 · read", kind: "" },
      { text: "ladder L1", kind: "accent" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "312 weekly users · 0.90 task success",
    access: "open",
    tagline: "returns and fees",
  },
  {
    id: "first-responder",
    slug: "first-responder",
    kind: "agent",
    name: "First responder",
    description:
      "Page to postmortem in the on-call team's chat: assembles the war room, reads with citations, acts under confirmation, mitigates under dual control.",
    road: "R2",
    lifecycle: "preview",
    icon: "w",
    glyph: "pulse",
    meta: [
      { text: "R2 · write", kind: "warn" },
      { text: "ladder L2", kind: "accent" },
      { text: "preview", kind: "warn" },
    ],
    footNote: "increment 1 on the sandbox · the origin of the collection's action loop",
    access: "request",
    requestKind: "access",
    tagline: "on-call, war room, first read",
    collection: true,
  },
  {
    id: "policy-and-procedures",
    slug: "policy-and-procedures",
    kind: "knowledge",
    name: "Policy and procedures",
    description: "Retrieval over runbooks, the policy manual and incidents, with provenance on every chunk.",
    road: "R5",
    lifecycle: "GA",
    icon: "m",
    glyph: "book",
    meta: [
      { text: "R5 · retrieval", kind: "" },
      { text: "internal", kind: "line" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "2,400 queries a week",
    access: "open",
  },
  {
    id: "compliance-narration",
    slug: "compliance-narration",
    kind: "agent",
    name: "Compliance narration",
    description: "Drafts return and recall narrations for a reviewer. Every draft is a labelled example.",
    road: "R4",
    lifecycle: "preview",
    icon: "p",
    glyph: "pen",
    meta: [
      { text: "R4 · drafts", kind: "" },
      { text: "confidential", kind: "line" },
      { text: "preview", kind: "warn" },
    ],
    footNote: "reviewer role needed",
    access: "request",
    requestKind: "role",
  },
  {
    id: "online-banking-assistant",
    slug: "online-banking-assistant",
    kind: "assistant",
    name: "Online banking assistant",
    description: "The customer-channel assistant on road R3, with handoff and templates. View only for staff.",
    road: "R3",
    lifecycle: "GA",
    icon: "a",
    glyph: "chat",
    meta: [
      { text: "R3 · customer", kind: "" },
      { text: "money · W1", kind: "warn" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "owner digital-channels",
    access: "view",
  },
  {
    id: "payments-exception-agent",
    slug: "payments-exception-agent",
    kind: "agent",
    name: "Payments exception agent",
    description: "Proposes hold releases and payee updates under dual control for the payments desk.",
    road: "R2",
    lifecycle: "GA",
    icon: "w",
    glyph: "bolt",
    meta: [
      { text: "R2 · write", kind: "warn" },
      { text: "ladder L2", kind: "accent" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "approver role needed",
    access: "request",
    requestKind: "role",
    tagline: "holds and payees, dual control",
  },
  {
    id: "sanctions-screening",
    slug: "sanctions-screening",
    kind: "tool",
    name: "Sanctions screening",
    description: "The position-5 screening client every money road calls. A tool, not an assistant.",
    road: "R1",
    lifecycle: "GA",
    icon: "m",
    glyph: "shield",
    meta: [
      { text: "tool · M", kind: "money" },
      { text: "contract v4", kind: "mono" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "called from harness only",
    access: "contract",
  },
  {
    id: "road-r2-template",
    slug: "road-r2-template",
    kind: "road",
    name: "R2 internal agent template",
    description: "crai new --road R2: the loop, gateway, elicitation and ladder wired; three weeks to sandbox.",
    road: "R2",
    lifecycle: "GA",
    icon: "",
    glyph: "layers",
    meta: [
      { text: "road · R2", kind: "line" },
      { text: "template v7", kind: "mono" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "reference consumer green",
    access: "view",
  },
  {
    id: "road-r4-template",
    slug: "road-r4-template",
    kind: "road",
    name: "R4 batch agent template",
    description: "Scheduled drafting into a review queue; per-item sessions and sampling; two weeks to sandbox.",
    road: "R4",
    lifecycle: "GA",
    icon: "",
    glyph: "layers",
    meta: [
      { text: "road · R4", kind: "line" },
      { text: "template v3", kind: "mono" },
      { text: "GA", kind: "ok" },
    ],
    footNote: "reference consumer green",
    access: "view",
  },
];

/** Everything Discover and the listing pages can show: the artboard's set plus the components collection. */
export const ALL_LISTINGS: ConsumerSummary[] = [...LISTINGS, ...COLLECTION_LISTINGS];

export function catalogFor(p: Principal): Catalog {
  const available = LISTINGS.filter((l) => ["employee-assistant", "investigation-triage", "policy-and-procedures", "compliance-narration"].includes(l.id)).map(
    (l) => ({ ...l, access: p.entitlements.includes(l.id) ? ("open" as const) : l.access === "open" ? ("request" as const) : l.access }),
  );
  return {
    availableCount: 4,
    available,
    listings: ALL_LISTINGS.map((l) =>
      l.collection ? l : { ...l, access: p.entitlements.includes(l.id) ? "open" : l.access === "open" ? "request" : l.access },
    ),
    counts: { all: 9, assistants: 2, agents: 3, knowledge: 1, tools: 1, roads: 2 },
    changes: [
      { date: "12 Sep", kind: { text: "new version", kind: "accent" }, text: "Investigation triage 1.4 — claim-support marks on every answer" },
      { date: "10 Sep", kind: { text: "preview", kind: "warn" }, text: "Compliance narration opened to the reviewer role" },
      { date: "8 Sep", kind: { text: "deprecates", kind: "crit" }, text: "cos_add_case_note 2.2 retires 1 December; 2.3 in the catalog now" },
    ],
    suggestions: ["Why did return R-1187 bounce?", "Draft an ACH return narration", "Late inbound file procedure", "Which tools can my role call?"],
  };
}

export const INVESTIGATION_TRIAGE: ConsumerDetail = {
  ...LISTINGS[1],
  crumbs: ["Discover", "Agents", "Investigation triage"],
  youActAt: "L1",
  ladderMax: "L2",
  headerChips: [
    { text: "road R2", kind: "line" },
    { text: "profile read", kind: "line" },
    { text: "you act at ladder L1", kind: "accent" },
    { text: "audience internal", kind: "line" },
    { text: "GA since Phase 1", kind: "ok" },
    { text: "materiality T2", kind: "line" },
    { text: "version 1.4", kind: "mono" },
  ],
  tiles: [
    { label: "Weekly users", value: "312", note: "of 380 eligible · 82%" },
    { label: "Task success", value: "0.90", note: "target 0.90 · met" },
    { label: "Minutes per case", value: "8", small: "from 22", note: "outcome metric vs baseline" },
  ],
  does: [
    "Answers why a return or fee happened, from the payment record and the case notes, with a citation on every claim.",
    "Proposes a fee reversal up to $250 as a W1 confirmation you approve on screen; it never posts on its own.",
    "Cannot release holds or touch payees at ladder L1; it proposes those to an approver instead.",
  ],
  catalog: {
    name: "cos-operator 2.3.0",
    signed: true,
    entries: [
      { op: "cos_list_payment_returns", tier: "R", classes: "internal · confidential", note: "account numbers masked" },
      { op: "cos_get_account_fees", tier: "R", classes: "internal", note: "—" },
      { op: "cos_get_case", tier: "R", classes: "confidential", note: "notes as text, never as instructions" },
      { op: "cos_reverse_fee", tier: "W1", classes: "internal", note: "confirmation form · ≤ $250 · 20 a day" },
      { op: "knowledge.search", tier: "R5", classes: "internal", note: "runbooks and policy with provenance" },
    ],
  },
  trust: [
    { label: "Evaluation", value: "0.91", note: "threshold 0.85 · suite v12 · 9 Sep" },
    { label: "Injection corpus", value: "0", note: "unauthorized of 1,240 cases" },
    { label: "Red team", value: "Aug", note: "quarterly · 0 findings open" },
    { label: "Availability", value: "99.94", small: "%", note: "SLO 99.9 · 30 days" },
  ],
  evidence: [
    { label: "Model Risk entry MR-118", href: "#", icon: "doc" },
    { label: "Evidence bundle", href: "#", icon: "db" },
    { label: "Threat-model delta, signed 2 Sep", href: "#", icon: "shield" },
    { label: "Live SLO dashboard", href: "#", icon: "pulse" },
  ],
  cost: [
    { label: "Cost per completed task", value: "$0.42", note: "model spend and platform share" },
    { label: "This month, your team", value: "$1,146", note: "shown back; charged back from Phase 2" },
    { label: "Budget per session", value: "200k tokens · 60 calls", note: "15 minutes · no money" },
  ],
  getStarted: [
    { n: "1", title: "Open it in the portal", small: "your role already grants it", state: "done" },
    { n: "2", title: "Enablement module · 12 minutes", small: "lesson 3 of 3 left: confirmations and step-up", state: "on" },
    { n: "3", title: "Your first case", small: "the pilot lead reviews your first ten turns", state: "" },
  ],
  owner: [
    { label: "owner", value: "team-payments-ops" },
    { label: "business owner", value: "D. Ruiz, Payments operations" },
    { label: "domain expert", value: "S. Okafor · 4 h a week labelling" },
    { label: "support", value: "P1 in 15 min · office hour Thu 11:00" },
    { label: "escalation", value: "platform lead" },
  ],
  versions: [
    { version: "1.4", state: "current", date: "12 Sep" },
    { version: "1.3", state: "supported", date: "2 Aug" },
    { version: "1.2", state: "retired", date: "1 Jul" },
  ],
  changelogHref: "https://catalog.crai.internal/consumers/investigation-triage/changelog",
};

export const DETAILS: Record<string, ConsumerDetail> = { "investigation-triage": INVESTIGATION_TRIAGE, ...COLLECTION_DETAILS };

/** The draft on the artboard: step 3 open, steps 1 and 2 done. Filed by gk. */
export const DRAFT_BRIEF: Brief = {
  id: "brf_7c1e",
  status: "draft",
  etag: 'W/"3"',
  createdBy: "u_gk",
  createdAt: "2026-09-12T09:14:00Z",
  updatedAt: "2026-09-14T16:02:00Z",
  currentStep: "dataAndTools",
  completed: ["useCase", "people"],
  content: {
    useCase: {
      name: "Payments returns triage for the collections desk",
      problem:
        "The collections desk reads each morning's payment returns out of COS one by one, opens the case notes, and decides by hand whether a fee should be reversed. About forty minutes before any decision is made.",
      channel: "operator",
      teamId: "team-payments-ops",
    },
    people: { businessOwner: "D. Ruiz, Payments operations", productOwner: "Gil Klainert", domainExpert: "S. Okafor", labellingHoursPerWeek: 4 },
    dataAndTools: {
      systems: [
        { id: "cos-payments", name: "COS · payments" },
        { id: "cos-case-notes", name: "COS · case notes" },
        { id: "knowledge-ops", name: "Knowledge index · ops" },
      ],
      tools: [
        { name: "cos_list_payment_returns", tier: "R", classes: ["internal", "confidential"] },
        { name: "cos_get_case", tier: "R", classes: ["confidential"] },
        { name: "cos_reverse_fee", tier: "W1", classes: ["internal"] },
      ],
      dataClasses: ["internal", "confidential"],
      tierCeiling: "R",
    },
    model: { need: "workhorse", classificationCeiling: "confidential", substitute: false },
    outcome: { metric: "minutes per case", unit: "minutes", baseline: 22, target: 12, measuredOn: "2026-09-01" },
    review: { acknowledged: false as unknown as true },
  },
};

export const REGISTRY_SYSTEMS: RegistrySystem[] = [
  { id: "cos-payments", name: "COS · payments", owner: "Payments engineering", contract: "recorded" },
  { id: "cos-case-notes", name: "COS · case notes", owner: "Operations engineering", contract: "recorded" },
  { id: "knowledge-ops", name: "Knowledge index · ops", owner: "Platform", contract: "recorded" },
  { id: "cos-customers", name: "COS · customers", owner: "Payments engineering", contract: "recorded" },
  { id: "ledger", name: "General ledger", owner: "Finance systems", contract: "recorded" },
  { id: "crm-service", name: "CRM · service desk", owner: "Customer operations", contract: "missing" },
];

export const REGISTRY_TOOLS: RegistryTool[] = [
  {
    name: "cos_list_payment_returns",
    systemId: "cos-payments",
    tier: "R",
    classes: ["internal", "confidential"],
    description: "Returns for a date range, with reason codes",
  },
  { name: "cos_get_case", systemId: "cos-case-notes", tier: "R", classes: ["confidential"], description: "One case with its notes and history" },
  { name: "cos_reverse_fee", systemId: "cos-payments", tier: "W1", classes: ["internal"], description: "Reverse a fee on a return · confirmation" },
  { name: "cos_close_case", systemId: "cos-case-notes", tier: "W1", classes: ["confidential"], description: "Close a case with a disposition · confirmation" },
  {
    name: "cos_search_customer",
    systemId: "cos-customers",
    tier: "R",
    classes: ["confidential", "restricted"],
    description: "Find a customer by identifier or name",
  },
  {
    name: "cos_post_adjustment",
    systemId: "cos-payments",
    tier: "W2",
    classes: ["internal", "confidential"],
    description: "Post a balance adjustment · dual control",
  },
  { name: "kb_search_ops", systemId: "knowledge-ops", tier: "R", classes: ["internal"], description: "Search the operations knowledge index" },
  { name: "ledger_get_entry", systemId: "ledger", tier: "R", classes: ["internal"], description: "Read a ledger entry" },
];

export const ESTIMATE: BriefEstimate = {
  modelSpendMonthly: 210,
  modelSpendBasis: "at 300 cases a week",
  reviewHours: 6,
  reviewNote: "Security and Privacy delta",
  platformShare: "included through Phase 1",
  basis: "platform calculator v3 · compared with actuals at each phase exit",
};

export const ROAD_R2_READ: RoadRecommendation = {
  road: "R2",
  title: "Read profile on an open road",
  subtitle: "agent with tools · ladder up to L1",
  selfService: true,
  note: "Registration, namespaces and the playground follow automatically. The platform lead confirms only the road, within two working days.",
  next: [
    { week: "W0", title: "Brief filed", small: "road assignment · system record opened" },
    { week: "W1", title: "Registered", small: "principal, budgets, playground · 2-day bootcamp" },
    { week: "W2", title: "Build with an embedded engineer", small: "repository from the road template" },
    { week: "W4", title: "Sandbox", small: "evaluation and corpus gates in CI" },
  ],
};

export function workspaceFor(p: Principal, briefs: Brief[]): Workspace {
  const draft = briefs.find((b) => b.status === "draft" && b.createdBy === p.id);
  return {
    header: {
      name: p.name,
      role: p.roles.includes("ops.lead") ? "ops.lead" : (p.roles[0] ?? "employee"),
      team: p.teams[0]?.id ?? "no team",
      costCentre: p.costCentre,
    },
    assistants: (
      [
        { consumerId: "employee-assistant", name: "Employee assistant", sub: "R2 · read · used today", lifecycle: "GA", ai: true },
        { consumerId: "investigation-triage", name: "Investigation triage", sub: "R2 · read · ladder L1 · 14 turns this week", lifecycle: "GA", ai: false },
        { consumerId: "policy-and-procedures", name: "Policy and procedures", sub: "R5 · 31 queries this week", lifecycle: "GA", ai: false },
      ] as Workspace["assistants"]
    ).filter((a) => p.entitlements.includes(a.consumerId)),
    teamConsumers: p.teams.some((t) => t.id === "team-payments-ops")
      ? [
          {
            id: "agent:investigation-triage",
            name: "agent:investigation-triage",
            status: { text: "production", kind: "ok" },
            step: 7,
            stepNote: "step 7 · operate · monthly review 1 Oct",
            pipe: ["done", "done", "done", "done", "done", "done", "done"],
            note: "time to sandbox 9 days · to production 38 days",
          },
          {
            id: "agent:compliance-narration",
            name: "agent:compliance-narration",
            status: { text: "sandbox", kind: "warn" },
            step: 4,
            stepNote: "step 4 · sandbox · corpus gate running",
            pipe: ["done", "done", "done", "on", "", "", ""],
            note: "labelling backlog 4 days · under the 2-week limit",
          },
          ...(draft
            ? [
                {
                  id: "collections-returns-triage",
                  name: "collections-returns-triage",
                  status: { text: "proposed", kind: "line" as const },
                  step: 1 as const,
                  stepNote: "step 1 · brief in draft",
                  pipe: ["on", "", "", "", "", "", ""] as Workspace["teamConsumers"][number]["pipe"],
                  note: `filed by you · ${draft.completed.length + 1} of 6 sections`,
                  briefId: draft.id,
                },
              ]
            : []),
        ]
      : [],
    requests: [],
    usage: {
      sandboxMonth: "$41.20",
      sandboxNote: "shown back, not charged",
      productionNote: `charged back to cost centre ${p.costCentre} from Phase 2`,
      playgroundToday: "$6.10",
      playgroundBudget: "$25.00",
      playgroundPct: 24,
    },
    playground: {
      gateway: "sandbox.gw.crai.internal",
      keyMasked: "crai_pg_…8f2a",
      fixtures: "COS payments · case notes · synthetic",
      example: "Run the 15-minute R2 example",
    },
  };
}

export const INITIAL_REQUESTS = [
  {
    id: "req_1",
    kind: "role" as const,
    consumerId: "compliance-narration",
    title: "Compliance narration · reviewer role",
    note: "with the platform lead · day 1 of 2",
    status: "pending" as const,
    createdAt: "2026-09-13T10:00:00Z",
  },
  {
    id: "req_2",
    kind: "ladder" as const,
    consumerId: "investigation-triage",
    title: "Ladder L2 on investigation triage",
    note: "with your lead, D. Ruiz · case-scoped",
    status: "pending" as const,
    createdAt: "2026-09-13T11:00:00Z",
  },
  {
    id: "req_3",
    kind: "access" as const,
    consumerId: "policy-and-procedures",
    title: "Policy and procedures",
    note: "granted by role 3 Sep",
    status: "granted" as const,
    createdAt: "2026-09-03T09:00:00Z",
  },
];

export const CONVERSATIONS: ConversationSummary[] = [
  { id: "cnv_1", title: "Late inbound file procedure", when: "today · 2 turns", assistantId: "employee-assistant" },
  { id: "cnv_2", title: "R-1187 return and fee", when: "today · via investigation triage", assistantId: "investigation-triage" },
  { id: "cnv_3", title: "Chargeback letter wording", when: "yesterday", assistantId: "employee-assistant" },
  { id: "cnv_4", title: "Cut-off times for wires", when: "Thursday", assistantId: "employee-assistant" },
];

/** Header line and chips per assistant, as the conversation card shows them. */
export const ASSISTANT_META: Record<string, Conversation["assistant"]> = {
  "employee-assistant": {
    name: "Employee assistant",
    sub: "reads what your role can read · never writes · session memory only",
    chips: [
      { text: "R2 · read", kind: "line" },
      { text: "internal", kind: "line" },
    ],
  },
  "investigation-triage": {
    name: "Investigation triage",
    sub: "returns and fees · proposes, you confirm · ladder L1",
    chips: [
      { text: "R2 · read", kind: "line" },
      { text: "ladder L1", kind: "accent" },
      { text: "confidential", kind: "model" },
    ],
  },
  "payments-exception-agent": {
    name: "Payments exception agent",
    sub: "hold releases and payee updates under dual control",
    chips: [
      { text: "R2 · write", kind: "warn" },
      { text: "ladder L2", kind: "accent" },
    ],
  },
};

export const CONVERSATION_1: Conversation = {
  id: "cnv_1",
  title: "Late inbound file procedure",
  assistantId: "employee-assistant",
  assistant: {
    name: "Employee assistant",
    sub: "reads what your role can read · never writes · session memory only",
    chips: [
      { text: "R2 · read", kind: "line" },
      { text: "internal", kind: "line" },
    ],
  },
  turns: [
    { id: "t1", role: "user", at: "09:41", views: [{ kind: "text", text: "What do we do when the ACH inbound file is late?", provenance: "system" }] },
    {
      id: "t2",
      role: "assistant",
      at: "09:41",
      sourcesLabel: "2 sources",
      views: [
        {
          kind: "text",
          provenance: "model",
          text: "If the inbound file has not arrived by 16:30 ET, open a P3 incident, tell the payments desk and hold posting until the file is reconciled.",
          claims: [
            { span: [39, 47], support: "cited", ref: "c1" },
            { span: [56, 67], support: "cited", ref: "c1" },
          ],
        },
        { kind: "citation", source: "Runbook · ACH inbound files §3", chunk_ref: "c1", classification: "internal" },
        { kind: "text", provenance: "model", text: " Returns that land after the two-banking-day window go to Compliance before they post." },
        { kind: "citation", source: "Policy manual · ACH returns §4.1", chunk_ref: "c2", classification: "confidential" },
        {
          kind: "text",
          provenance: "model",
          text: "The last time this happened was March, IR-2211: an upstream certificate rotation; posting resumed at 19:12 and a 14-day expiry alert was added.",
          claims: [{ span: [32, 46], support: "cited", ref: "c3" }],
        },
        { kind: "citation", source: "Incident IR-2211", chunk_ref: "c3", classification: "internal" },
        { kind: "feedback", seq: 2, question: "Did this answer your question?" },
      ],
      sources: [
        { text: "runbook · internal", kind: "line" },
        { text: "policy manual · confidential", kind: "model" },
        { text: "incident · internal", kind: "line" },
      ],
    },
  ],
};
