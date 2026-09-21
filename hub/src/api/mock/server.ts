import type { Transport } from "../client";
import type { Problem } from "../errors";
import { briefContentSchema, issuesToFieldErrors } from "../schemas";
import { ownerHandle, permits } from "../../auth/permits";
import type { AccessRequest, Brief, ConsumerDetail, Conversation, ShelfEntry, ShelfRole, ShelfSignoffRecord, TurnEvent, Workspace } from "../types";
import {
  ASSISTANT_META,
  CONVERSATION_1,
  CONVERSATIONS,
  DETAILS,
  DRAFT_BRIEF,
  ESTIMATE,
  INITIAL_REQUESTS,
  ALL_LISTINGS,
  PRINCIPALS,
  SHELF,
  ROAD_R2_READ,
  catalogFor,
  workspaceFor,
  REGISTRY_SYSTEMS,
  REGISTRY_TOOLS,
} from "./fixtures";
import { ask as guideAsk } from "./guideRules";
import { withBaseline } from "../baseline";
import type { GuideAudience } from "../types";

/**
 * An in-process Hub API for development, demos and tests.
 *
 * It is a `Transport`, so the real `ApiClient` runs against it unchanged:
 * bearer tokens, problem+json errors, If-Match, idempotency keys and the SSE
 * turn stream all behave as the contract in `api/openapi.yaml` describes.
 * State lives for the page's lifetime; a reload restores the fixtures.
 */

type Handler = (ctx: {
  params: Record<string, string>;
  url: URL;
  body: unknown;
  principal: NonNullable<ReturnType<typeof principalOf>>;
  req: Request;
}) => Response | Promise<Response>;

const routes: Array<{ method: string; pattern: RegExp; keys: string[]; handler: Handler; anonymous?: boolean }> = [];

function route(method: string, path: string, handler: Handler, opts: { anonymous?: boolean } = {}) {
  const keys: string[] = [];
  const pattern = new RegExp(
    "^" +
      path.replace(/:(\w+)/g, (_, k) => {
        keys.push(k);
        return "([^/]+)";
      }) +
      "$",
  );
  routes.push({ method, pattern, keys, handler, ...opts });
}

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { status: 200, ...init, headers: { "Content-Type": "application/json", ...(init.headers ?? {}) } });

const problem = (status: number, p: Problem) =>
  new Response(JSON.stringify({ status, ...p }), { status, headers: { "Content-Type": "application/problem+json" } });

function principalOf(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  const m = /^Bearer mock\.(\w+)$/.exec(auth);
  return m ? PRINCIPALS[m[1]] : undefined;
}

/* ---------- state ---------- */
const state = {
  briefs: new Map<string, Brief>([[DRAFT_BRIEF.id, structuredClone(DRAFT_BRIEF)]]),
  requests: [...INITIAL_REQUESTS] as AccessRequest[],
  conversations: new Map<string, Conversation>([[CONVERSATION_1.id, structuredClone(CONVERSATION_1)]]),
  prefs: new Map<string, (typeof PRINCIPALS)[string]["preferences"]>(),
  idempotency: new Map<string, Response>(),
  /** Sign-offs recorded through the hub this session; the export hands them to the shelf tool. */
  signoffs: [] as ShelfSignoffRecord[],
  seq: 100,
};

const bump = (etag: string) => `W/"${Number(etag.replace(/\D/g, "")) + 1}"`;
const nowIso = () => new Date().toISOString();

/* ---------- routes ---------- */

route("GET", "/me", ({ principal }) => json({ ...principal, preferences: state.prefs.get(principal.id) ?? principal.preferences }));

route("PUT", "/me/preferences", ({ principal, body }) => {
  state.prefs.set(principal.id, body as (typeof PRINCIPALS)[string]["preferences"]);
  return json({ ...principal, preferences: body });
});

route("GET", "/catalog", ({ principal }) => json(catalogFor(principal)));

route("GET", "/catalog/search", ({ url, principal }) => {
  const q = (url.searchParams.get("q") ?? "").toLowerCase();
  const hits = catalogFor(principal).listings.filter((l) => `${l.name} ${l.description} ${l.road} ${l.kind}`.toLowerCase().includes(q));
  return json(hits);
});

route("GET", "/consumers/:slug", ({ params, principal }) => {
  const summary = ALL_LISTINGS.find((l) => l.slug === params.slug);
  if (!summary) return problem(404, { title: "Not found", detail: "No listing with that name." });
  const detail = DETAILS[params.slug];
  const youActAt = principal.ladder === "L0" ? "L0" : (detail?.youActAt ?? "L1");
  // Access is resolved per person: an "open" listing the person is not entitled to is one they may request.
  const resolve = (id: string, access: ConsumerDetail["access"]) =>
    summary.collection ? access : principal.entitlements.includes(id) ? "open" : access === "open" ? "request" : access;
  return json(
    detail
      ? { ...detail, youActAt, access: resolve(detail.id, detail.access) }
      : {
          ...summary,
          crumbs: ["Discover", summary.kind === "agent" ? "Agents" : summary.kind === "assistant" ? "Assistants" : "Catalog", summary.name],
          youActAt,
          ladderMax: "L1",
          headerChips: summary.meta,
          access: resolve(summary.id, summary.access),
          tiles: [],
          does: [summary.description],
          catalog: { name: "—", signed: false, entries: [] },
          trust: [],
          evidence: [],
          cost: [],
          getStarted: [],
          owner: [],
          versions: [],
          changelogHref: "#",
        },
  );
});

route("GET", "/me/requests", ({ principal }) => json(principal.id === "u_gk" ? state.requests : state.requests.filter((r) => r.id.startsWith("req_new"))));

route("POST", "/me/requests", ({ principal, body }) => {
  const b = body as { kind: AccessRequest["kind"]; consumerId?: string; ladder?: string; reason?: string };
  const listing = ALL_LISTINGS.find((l) => l.id === b.consumerId);
  if (b.kind === "ladder" && b.ladder && ["L0", "L1", "L2", "L3"].indexOf(b.ladder) > ["L0", "L1", "L2", "L3"].indexOf(principal.ladder)) {
    return problem(403, {
      title: "Above your ceiling",
      detail: `Your own ladder is ${principal.ladder}; ask your lead to raise it first.`,
      code: "ladder.above",
    });
  }
  const r: AccessRequest = {
    id: `req_new_${state.requests.length + 1}`,
    kind: b.kind,
    consumerId: b.consumerId,
    title:
      b.kind === "ladder"
        ? `Ladder ${b.ladder} on ${listing?.name ?? b.consumerId}`
        : `${listing?.name ?? b.consumerId} · ${b.kind === "role" ? "reviewer role" : "access"}`,
    note: "with your lead · day 1 of 2",
    status: "pending",
    createdAt: nowIso(),
  };
  state.requests.unshift(r);
  return json(r, { status: 201 });
});

route("GET", "/me/workspace", ({ principal }) => {
  const ws: Workspace = workspaceFor(principal, [...state.briefs.values()]);
  ws.requests = principal.id === "u_gk" ? state.requests : state.requests.filter((r) => r.id.startsWith("req_new"));
  return json(ws);
});

route("POST", "/me/playground/rotate", () => json({ keyMasked: `crai_pg_…${Math.random().toString(16).slice(2, 6)}` }));

/* ---------- the shelf: sign-offs and onboarding ---------- */

const ROLES: ShelfRole[] = ["owner", "ai_security"];

/** The manifest's facts plus what this session recorded, and which roles this person may sign for. */
function shelfEntry(name: string, principal: (typeof PRINCIPALS)[string]): ShelfEntry | undefined {
  const r = SHELF.find((s) => s.name === name);
  if (!r) return undefined;
  const recorded: ShelfEntry["recorded"] = {};
  for (const s of state.signoffs) if (s.component === name && s.version === r.version) recorded[s.role] = s;
  const youMaySign = ROLES.filter((role) => permits(principal, "shelf.sign", { signoffRole: role, owner: r.owner }));
  return { ...r, recorded, youMaySign };
}

route("GET", "/shelf", ({ principal }) => json(SHELF.map((r) => shelfEntry(r.name, principal))));

route("GET", "/shelf/signoffs/export", () =>
  json({ generatedAt: nowIso(), apply: "python3 tools/shelf.py --apply-signoffs shelf-signoffs.json", signoffs: state.signoffs }),
);

route("GET", "/shelf/:name", ({ params, principal }) => {
  const e = shelfEntry(params.name, principal);
  return e ? json(e) : problem(404, { title: "Not found", detail: "No component with that name is on the shelf." });
});

route("POST", "/shelf/:name/signoffs", ({ params, principal, body }) => {
  const r = SHELF.find((s) => s.name === params.name);
  if (!r) return problem(404, { title: "Not found", detail: "No component with that name is on the shelf." });
  const b = (body ?? {}) as { role?: ShelfRole; attest?: Record<string, unknown>; usedIn?: string; note?: string };
  if (!b.role || !ROLES.includes(b.role)) return problem(422, { title: "Not valid", detail: "role must be owner or ai_security.", code: "validation" });
  if (!permits(principal, "shelf.sign", { signoffRole: b.role, owner: r.owner })) {
    return problem(403, {
      title: b.role === "owner" ? "Not the owner" : "Not an AI security engineer",
      detail:
        b.role === "owner"
          ? `The manifest names ${r.owner} as the owner; you are ${ownerHandle(principal)}.`
          : "The ai.security role is granted by the security team lead on your platform principal.",
      code: "shelf.role",
    });
  }
  if (r.status !== "ready")
    return problem(409, { title: "Not ready", detail: `The component is ${r.status}; a sign-off needs a ready component.`, code: "shelf.status" });
  const keys = ["testsGreen", "exampleRun", "walkthroughRead", "rulesRead"] as const;
  const missing = keys.filter((k) => b.attest?.[k] !== true);
  if (missing.length) {
    return problem(422, {
      title: "Every attestation is required",
      detail: `Not ticked: ${missing.join(", ")}.`,
      code: "validation",
      errors: Object.fromEntries(missing.map((k) => [`attest.${k}`, ["required"]])),
    });
  }
  const usedIn = (b.usedIn ?? "").trim();
  if (b.role === "owner" && r.usedIn.length === 0 && !usedIn) {
    return problem(422, {
      title: "Where was it used?",
      detail: "The owner signs after one real use; name the project.",
      code: "validation",
      errors: { usedIn: ["required"] },
    });
  }
  const already =
    r.signoff[b.role]?.version === r.version || state.signoffs.some((s) => s.component === r.name && s.role === b.role && s.version === r.version);
  if (already)
    return problem(409, {
      title: "Already signed",
      detail: `The ${b.role === "owner" ? "owner" : "AI security"} sign-off at ${r.version} is already recorded.`,
      code: "shelf.signed",
    });
  const rec: ShelfSignoffRecord = {
    id: `so_${state.signoffs.length + 1}`,
    component: r.name,
    role: b.role,
    by: `${principal.name} <${principal.email}>`,
    email: principal.email,
    date: nowIso().slice(0, 10),
    version: r.version,
    usedIn: usedIn || undefined,
    note: (b.note ?? "").trim() || undefined,
    attest: { testsGreen: true, exampleRun: true, walkthroughRead: true, rulesRead: true },
    recordedAt: nowIso(),
  };
  state.signoffs.push(rec);
  return json(rec, { status: 201 });
});

route("GET", "/registry/systems", () => json(REGISTRY_SYSTEMS));
route("GET", "/registry/tools", () => json(REGISTRY_TOOLS));

route("GET", "/briefs", ({ principal }) =>
  json([...state.briefs.values()].filter((b) => b.createdBy === principal.id || principal.roles.includes("platform.lead"))),
);

route("POST", "/briefs", ({ principal }) => {
  const id = `brf_${Math.random().toString(16).slice(2, 6)}`;
  const b: Brief = {
    id,
    status: "draft",
    etag: 'W/"1"',
    createdBy: principal.id,
    createdAt: nowIso(),
    updatedAt: nowIso(),
    currentStep: "useCase",
    completed: [],
    content: {
      useCase: { name: "", problem: "", channel: "operator", teamId: principal.teams[0]?.id ?? "" },
      people: { businessOwner: "", productOwner: principal.name, domainExpert: "", labellingHoursPerWeek: 0 },
      dataAndTools: { systems: [], tools: [], dataClasses: ["internal"], tierCeiling: "R" },
      model: { need: "workhorse", classificationCeiling: "internal", substitute: false },
      outcome: { metric: "", unit: "", baseline: 0, target: 0, measuredOn: "" },
      review: { acknowledged: false as unknown as true },
    },
  };
  state.briefs.set(id, b);
  return json(b, { status: 201 });
});

const loadBrief = (id: string, principal: { id: string; roles: string[] }) => {
  const b = state.briefs.get(id);
  if (!b || (b.createdBy !== principal.id && !principal.roles.includes("platform.lead"))) return undefined;
  return b;
};

route("GET", "/briefs/:id", ({ params, principal }) => {
  const b = loadBrief(params.id, principal);
  return b ? json(b) : problem(404, { title: "Not found", detail: "No brief with that id, or you cannot see it." });
});

route("PATCH", "/briefs/:id", ({ params, principal, body, req }) => {
  const b = loadBrief(params.id, principal);
  if (!b) return problem(404, { title: "Not found" });
  if (b.status !== "draft" && b.status !== "needs_info") return problem(409, { title: "Not editable", detail: "A filed brief cannot be edited." });
  const ifMatch = req.headers.get("if-match");
  if (ifMatch && ifMatch !== b.etag)
    return problem(409, { title: "Changed elsewhere", detail: "This draft was saved from another tab. Reload to see the latest version." });
  const patch = body as { content?: Partial<Brief["content"]>; currentStep?: Brief["currentStep"]; completed?: Brief["completed"] };
  if (patch.content) b.content = { ...b.content, ...patch.content } as Brief["content"];
  if (patch.currentStep) b.currentStep = patch.currentStep;
  if (patch.completed) b.completed = patch.completed;
  b.updatedAt = nowIso();
  b.etag = bump(b.etag);
  return json(b);
});

route("POST", "/briefs/:id/estimate", ({ body }) => {
  const c = body as Brief["content"];
  const tools = c.dataAndTools?.tools?.length ?? 3;
  const need = c.model?.need ?? "workhorse";
  const factor = need === "frontier" ? 2.4 : need === "utility" ? 0.4 : need === "none" ? 0 : 1;
  return json({ ...ESTIMATE, modelSpendMonthly: Math.round(70 * tools * factor), reviewHours: c.dataAndTools?.dataClasses?.includes("confidential") ? 6 : 3 });
});

route("POST", "/briefs/:id/road", ({ body }) => {
  const c = body as Brief["content"];
  const ceiling = c.dataAndTools?.tierCeiling ?? "R";
  const channel = c.useCase?.channel ?? "operator";
  if (channel === "customer" || channel === "partner")
    return json({
      ...ROAD_R2_READ,
      road: "R3",
      title: "Customer and partner assistant",
      subtitle: "federated identity · entitlements · step-up",
      selfService: false,
      note: "R3 opens in Phase 5. The platform lead confirms the brief and Compliance reviews the channel templates.",
    });
  if (channel === "batch")
    return json({
      ...ROAD_R2_READ,
      road: "R4",
      title: "Batch agent with a review queue",
      subtitle: "drafts for a human · ladder L1",
      selfService: true,
      note: "Every output lands in a review queue; a sampling rule keeps a person on at least 5 percent of drafts.",
    });
  if (ceiling !== "R")
    return json({
      ...ROAD_R2_READ,
      title: `Write profile (${ceiling}) on road R2`,
      subtitle: "agent with tools · confirmation or dual control",
      selfService: false,
      note: "A write profile needs the platform lead's confirmation of the brief, and the second line reviews the delta before staging.",
    });
  return json(ROAD_R2_READ);
});

route("POST", "/briefs/:id/file", ({ params, principal, req }) => {
  const b = loadBrief(params.id, principal);
  if (!b) return problem(404, { title: "Not found" });
  const ifMatch = req.headers.get("if-match");
  if (ifMatch && ifMatch !== b.etag) return problem(409, { title: "Changed elsewhere", detail: "Reload before filing." });
  const parsed = briefContentSchema.safeParse(b.content);
  if (!parsed.success)
    return problem(422, {
      title: "The brief is not complete",
      detail: "Some sections need attention before it can be filed.",
      errors: issuesToFieldErrors(parsed.error.issues),
    });
  b.content = withBaseline(b.content); // the harness baseline is the record's, not the form's
  const write = b.content.dataAndTools.tierCeiling !== "R";
  if (write && !principal.roles.some((r) => r === "ops.lead" || r === "platform.lead")) {
    return problem(403, {
      title: "Lead confirmation needed",
      detail: "A write profile is filed by your team lead. Save the draft and ask them to file it.",
      code: "brief.lead_required",
    });
  }
  b.status = "filed";
  b.road = write ? "R2" : "R2";
  b.etag = bump(b.etag);
  b.updatedAt = nowIso();
  return json(b);
});

/* ---------- the guide ---------- */

route("POST", "/guide/ask", ({ body, principal }) => {
  const b = (body ?? {}) as { question?: unknown; audience?: unknown; page?: unknown };
  const question = typeof b.question === "string" ? b.question.slice(0, 2000) : "";
  const audiences: GuideAudience[] = ["engineer", "leadership", "employee"];
  // The same default the service applies: a lead with no team of their own is treated as leadership, everyone else as an engineer.
  const fallback: GuideAudience = principal.roles.includes("platform.lead") && !principal.teams.length ? "leadership" : "engineer";
  const audience = audiences.includes(b.audience as GuideAudience) ? (b.audience as GuideAudience) : fallback;
  return json(guideAsk(question, audience, typeof b.page === "string" ? b.page : undefined));
});

route("GET", "/conversations", ({ principal }) =>
  json(
    [
      ...[...state.conversations.values()]
        .filter((c) => !CONVERSATIONS.some((s) => s.id === c.id))
        .map((c) => ({ id: c.id, title: c.title, when: "just now", assistantId: c.assistantId })),
      ...CONVERSATIONS,
    ].filter((c) => principal.entitlements.includes(c.assistantId)),
  ),
);

route("GET", "/conversations/:id", ({ params }) => {
  const c = state.conversations.get(params.id);
  return c ? json(c) : problem(404, { title: "Not found" });
});

route("POST", "/conversations", ({ body, principal }) => {
  const { assistantId } = body as { assistantId: string };
  const id = `cnv_${Math.random().toString(16).slice(2, 6)}`;
  const meta = ASSISTANT_META[assistantId];
  if (!meta) return problem(404, { title: "Not found", detail: "No assistant with that id." });
  if (!principal.entitlements.includes(assistantId))
    return problem(403, { title: "Not entitled", detail: "Your role does not open this assistant.", code: "entitlement.missing" });
  const c: Conversation = { id, title: "New conversation", assistantId, assistant: meta, turns: [] };
  state.conversations.set(id, c);
  return json(c, { status: 201 });
});

route("POST", "/conversations/:id/turns", ({ params, body, req }) => {
  const c = state.conversations.get(params.id);
  if (!c) return problem(404, { title: "Not found" });
  const { text } = body as { text: string };
  const at = new Date().toTimeString().slice(0, 5);
  c.turns.push({ id: `t${++state.seq}`, role: "user", at, views: [{ kind: "text", text, provenance: "system" }] });
  if (c.title === "New conversation") c.title = text.length > 48 ? `${text.slice(0, 45)}…` : text;
  const events: TurnEvent[] = [
    {
      seq: ++state.seq,
      view: { kind: "tool_call", tool: "knowledge.search", state: "allowed", tier: "R", args_summary: [{ label: "query", value: text.slice(0, 40) }], ms: 118 },
    },
    { seq: ++state.seq, view: { kind: "text", provenance: "model", text: "Here is what the runbook says about that. " } },
    {
      seq: ++state.seq,
      view: {
        kind: "text",
        provenance: "model",
        text: "The procedure is owned by payments operations and reviewed quarterly; the current version is dated 2 September.",
        claims: [{ span: [59, 78], support: "cited", ref: "c9" }],
      },
    },
    { seq: ++state.seq, view: { kind: "citation", source: "Runbook · payments operations §1", chunk_ref: "c9", classification: "internal" } },
    { seq: ++state.seq, view: { kind: "budget", tokens: [41210, 200000], tool_calls: [8, 60], time_s: [214, 900] } },
    { seq: ++state.seq, view: { kind: "feedback", seq: state.seq, question: "Did this answer your question?" } },
  ];
  const assistantTurn = { id: `t${state.seq}`, role: "assistant" as const, at, views: [] as TurnEvent["view"][] };
  c.turns.push(assistantTurn);
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const ev of events) {
        if (req.signal.aborted) {
          assistantTurn.views.push({ kind: "stop", reason: "human.interrupt", message: "Stopped." });
          break;
        }
        await new Promise((r) => setTimeout(r, 160));
        assistantTurn.views.push(ev.view);
        controller.enqueue(encoder.encode(`event: view\ndata: ${JSON.stringify(ev)}\n\n`));
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } });
});

route("POST", "/conversations/:id/feedback", () => new Response(null, { status: 204 }));
route("POST", "/conversations/:id/handoff", () => json({ route: "human", expected_wait_s: 240 }));

/* ---------- the transport ---------- */

export const mockTransport: Transport = async (req) => {
  const url = new URL(req.url, typeof location !== "undefined" ? location.origin : "http://localhost");
  const path = url.pathname.replace(/^\/api/, "") || "/";
  const match = routes.find((r) => r.method === req.method && r.pattern.test(path));
  if (!match) return problem(404, { title: "Not found", detail: `No route ${req.method} ${path}` });
  const principal = principalOf(req);
  if (!principal && !match.anonymous) return problem(401, { title: "Unauthenticated", code: "unauthenticated" });
  const key = req.headers.get("idempotency-key");
  if (key && state.idempotency.has(key)) return state.idempotency.get(key)!.clone();
  const m = match.pattern.exec(path)!;
  const params = Object.fromEntries(match.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text().then((t) => (t ? JSON.parse(t) : undefined));
  await new Promise((r) => setTimeout(r, 40 + Math.random() * 60)); // a little latency, so loading states are real
  const res = await match.handler({ params, url, body, principal: principal!, req });
  if (key && res.status < 500 && !res.headers.get("content-type")?.includes("event-stream")) state.idempotency.set(key, res.clone());
  return res;
};

/** Test hook: reset in-memory state to the fixtures. */
export function resetMockState() {
  state.briefs = new Map([[DRAFT_BRIEF.id, structuredClone(DRAFT_BRIEF)]]);
  state.requests = [...INITIAL_REQUESTS];
  state.conversations = new Map([[CONVERSATION_1.id, structuredClone(CONVERSATION_1)]]);
  state.prefs.clear();
  state.idempotency.clear();
  state.signoffs = [];
}
