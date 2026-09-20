import type { ApiClient } from "./client";
import type {
  AccessRequest,
  Brief,
  BriefContent,
  BriefEstimate,
  BriefStepKey,
  Catalog,
  ConsumerDetail,
  Conversation,
  ConversationSummary,
  GuideAnswer,
  GuideAudience,
  Preferences,
  Principal,
  RegistrySystem,
  RegistryTool,
  RoadRecommendation,
  ShelfAttestation,
  ShelfEntry,
  ShelfExport,
  ShelfRole,
  ShelfSignoffRecord,
  TurnEvent,
  Workspace,
} from "./types";

/**
 * Every call the Hub makes, typed. This file is the front end's half of the
 * API contract; `api/openapi.yaml` is the server team's half, and the two are
 * kept in step by hand until a generated client replaces this file (the
 * platform's contract registry generates TypeScript clients, spec §4.11).
 */
export function endpoints(api: ApiClient) {
  return {
    me: {
      get: (signal?: AbortSignal) => api.get<Principal>("/me", { signal }),
      updatePreferences: (prefs: Preferences) => api.put<Principal>("/me/preferences", prefs),
    },
    catalog: {
      get: (signal?: AbortSignal) => api.get<Catalog>("/catalog", { signal }),
      search: (q: string, signal?: AbortSignal) => api.get<Catalog["listings"]>(`/catalog/search?q=${encodeURIComponent(q)}`, { signal }),
    },
    consumers: {
      get: (slug: string, signal?: AbortSignal) => api.get<ConsumerDetail>(`/consumers/${encodeURIComponent(slug)}`, { signal }),
    },
    requests: {
      list: (signal?: AbortSignal) => api.get<AccessRequest[]>("/me/requests", { signal }),
      create: (body: { kind: AccessRequest["kind"]; consumerId?: string; ladder?: string; reason?: string }, idempotencyKey: string) =>
        api.post<AccessRequest>("/me/requests", body, { idempotencyKey }),
    },
    workspace: {
      get: (signal?: AbortSignal) => api.get<Workspace>("/me/workspace", { signal }),
      rotatePlaygroundKey: (idempotencyKey: string) => api.post<{ keyMasked: string }>("/me/playground/rotate", undefined, { idempotencyKey }),
    },
    shelf: {
      /** Every component of the collection with its version, sign-offs and onboarding stage. */
      list: (signal?: AbortSignal) => api.get<ShelfEntry[]>("/shelf", { signal }),
      get: (name: string, signal?: AbortSignal) => api.get<ShelfEntry>(`/shelf/${encodeURIComponent(name)}`, { signal }),
      /** Record a sign-off; the server checks the role and that every attestation is ticked. */
      sign: (name: string, body: { role: ShelfRole; attest: ShelfAttestation; usedIn?: string; note?: string }, idempotencyKey: string) =>
        api.post<ShelfSignoffRecord>(`/shelf/${encodeURIComponent(name)}/signoffs`, body, { idempotencyKey }),
      /** Sign-offs recorded here and not yet in a manifest, as the file the shelf tool applies. */
      export: (signal?: AbortSignal) => api.get<ShelfExport>("/shelf/signoffs/export", { signal }),
    },
    registry: {
      systems: (signal?: AbortSignal) => api.get<RegistrySystem[]>("/registry/systems", { signal }),
      tools: (signal?: AbortSignal) => api.get<RegistryTool[]>("/registry/tools", { signal }),
    },
    briefs: {
      list: (signal?: AbortSignal) => api.get<Brief[]>("/briefs", { signal }),
      get: (id: string, signal?: AbortSignal) => api.get<Brief>(`/briefs/${id}`, { signal }),
      create: (idempotencyKey: string) => api.post<Brief>("/briefs", {}, { idempotencyKey }),
      /** Autosave: partial content plus the step the person is on. Returns the new etag. */
      save: (id: string, etag: string, patch: { content?: Partial<BriefContent>; currentStep?: BriefStepKey; completed?: BriefStepKey[] }) =>
        api.patch<Brief>(`/briefs/${id}`, patch, { ifMatch: etag }),
      estimate: (id: string, content: BriefContent, signal?: AbortSignal) => api.post<BriefEstimate>(`/briefs/${id}/estimate`, content, { signal }),
      road: (id: string, content: BriefContent, signal?: AbortSignal) => api.post<RoadRecommendation>(`/briefs/${id}/road`, content, { signal }),
      file: (id: string, etag: string, idempotencyKey: string) => api.post<Brief>(`/briefs/${id}/file`, undefined, { ifMatch: etag, idempotencyKey }),
    },
    guide: {
      /** Ask the guide. The answer comes from the collection's own pages with sources; `page` lets it skip suggesting where the person already is. */
      ask: (body: { question: string; audience?: GuideAudience; page?: string }, signal?: AbortSignal) =>
        api.post<GuideAnswer>("/guide/ask", body, { signal }),
    },
    conversations: {
      list: (signal?: AbortSignal) => api.get<ConversationSummary[]>("/conversations", { signal }),
      get: (id: string, signal?: AbortSignal) => api.get<Conversation>(`/conversations/${id}`, { signal }),
      create: (assistantId: string, idempotencyKey: string) => api.post<Conversation>("/conversations", { assistantId }, { idempotencyKey }),
      /**
       * Send a turn and stream the harness's view events back (SSE). The
       * caller consumes `TurnEvent`s as they arrive and may abort to stop the
       * turn, which the server records as `human.interrupt` (PLT-HAR-29).
       */
      send: (id: string, text: string, idempotencyKey: string, signal: AbortSignal) =>
        streamTurn(api, `/conversations/${id}/turns`, { text }, idempotencyKey, signal),
      feedback: (id: string, seq: number, answered: boolean) => api.post<void>(`/conversations/${id}/feedback`, { seq, answered }),
      handoff: (id: string, idempotencyKey: string) =>
        api.post<{ route: string; expected_wait_s?: number }>(`/conversations/${id}/handoff`, undefined, { idempotencyKey }),
    },
  };
}

export type Endpoints = ReturnType<typeof endpoints>;

/** Parse a `text/event-stream` body into TurnEvents. Works for real fetch and the mock transport alike. */
async function* streamTurn(api: ApiClient, path: string, body: unknown, idempotencyKey: string, signal: AbortSignal): AsyncGenerator<TurnEvent> {
  const res = await api.raw(path, { method: "POST", body, signal, idempotencyKey, accept: "text/event-stream" });
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const data = frame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("\n");
        if (data) yield JSON.parse(data) as TurnEvent;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
