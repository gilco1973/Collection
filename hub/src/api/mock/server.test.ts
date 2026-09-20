import { beforeEach, describe, expect, it } from "vitest";
import { ApiClient } from "../client";
import { endpoints } from "../endpoints";
import { ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationError } from "../errors";
import { mockTransport, resetMockState } from "./server";

const clientAs = (persona?: string) => endpoints(new ApiClient("/api", mockTransport, async () => (persona ? `mock.${persona}` : undefined)));

describe("mock API contract", () => {
  beforeEach(() => resetMockState());

  it("refuses anonymous calls with 401", async () => {
    await expect(clientAs().me.get()).rejects.toBeInstanceOf(UnauthorizedError);
  });

  it("resolves the principal from the bearer token", async () => {
    const me = await clientAs("gk").me.get();
    expect(me.id).toBe("u_gk");
    expect(me.roles).toContain("ops.lead");
  });

  it("resolves access per person on the catalog and listings", async () => {
    const gk = await clientAs("gk").catalog.get();
    expect(gk.available.find((c) => c.id === "investigation-triage")?.access).toBe("open");
    const emp = await clientAs("employee").catalog.get();
    expect(emp.available.find((c) => c.id === "investigation-triage")?.access).toBe("request");
    const detail = await clientAs("employee").consumers.get("investigation-triage");
    expect(detail.access).toBe("request");
    await expect(clientAs("employee").consumers.get("nope")).rejects.toBeInstanceOf(NotFoundError);
  });

  it("bumps the etag on save and refuses a stale If-Match with 409", async () => {
    const api = clientAs("gk");
    const b = await api.briefs.get("brf_7c1e");
    const saved = await api.briefs.save(b.id, b.etag, { currentStep: "model" });
    expect(saved.etag).not.toBe(b.etag);
    expect(saved.currentStep).toBe("model");
    await expect(api.briefs.save(b.id, b.etag, { currentStep: "outcome" })).rejects.toBeInstanceOf(ConflictError);
  });

  it("hides another person's draft", async () => {
    await expect(clientAs("employee").briefs.get("brf_7c1e")).rejects.toBeInstanceOf(NotFoundError);
    expect(await clientAs("platform").briefs.get("brf_7c1e")).toMatchObject({ id: "brf_7c1e" });
  });

  it("validates on file with the same schema and applies the lead rule", async () => {
    const api = clientAs("gk");
    let b = await api.briefs.get("brf_7c1e");
    await expect(api.briefs.file(b.id, b.etag, "k1")).rejects.toBeInstanceOf(ValidationError);
    b = await api.briefs.save(b.id, b.etag, {
      content: { ...b.content, dataAndTools: { ...b.content.dataAndTools, tierCeiling: "W1" }, review: { acknowledged: true } },
    });
    const filed = await api.briefs.file(b.id, b.etag, "k2");
    expect(filed.status).toBe("filed");
    // An employee's own write-profile brief needs a lead.
    const emp = clientAs("employee");
    const mine = await emp.briefs.create("k3");
    const draft = await emp.briefs.save(mine.id, mine.etag, {
      content: { ...b.content, useCase: { ...b.content.useCase, teamId: "team-x" }, people: { ...b.content.people, labellingHoursPerWeek: 2 } },
    });
    await expect(emp.briefs.file(draft.id, draft.etag, "k4")).rejects.toBeInstanceOf(ForbiddenError);
  });

  it("replays an idempotent mutation instead of repeating it", async () => {
    const api = clientAs("gk");
    const a = await api.briefs.create("same-key");
    const b = await api.briefs.create("same-key");
    expect(b.id).toBe(a.id);
    expect((await api.briefs.list()).filter((x) => x.id === a.id)).toHaveLength(1);
  });

  it("refuses a ladder request above the person's ceiling", async () => {
    await expect(clientAs("investigator").requests.create({ kind: "ladder", consumerId: "investigation-triage", ladder: "L2" }, "k5")).rejects.toBeInstanceOf(
      ForbiddenError,
    );
    const ok = await clientAs("gk").requests.create({ kind: "ladder", consumerId: "investigation-triage", ladder: "L2" }, "k6");
    expect(ok.status).toBe("pending");
  });

  it("streams a turn as view events and records a stop on abort", async () => {
    const api = clientAs("gk");
    const kinds: string[] = [];
    for await (const ev of api.conversations.send("cnv_1", "cut-off for wires?", "k7", new AbortController().signal)) kinds.push(ev.view.kind);
    expect(kinds).toEqual(["tool_call", "text", "text", "citation", "budget", "feedback"]);
    const c = await api.conversations.get("cnv_1");
    expect(c.turns.at(-2)?.role).toBe("user");
    expect(c.turns.at(-1)?.views.map((v) => v.kind)).toEqual(kinds);
    const ctrl = new AbortController();
    const seen: string[] = [];
    try {
      for await (const ev of api.conversations.send("cnv_1", "and ACH?", "k8", ctrl.signal)) {
        seen.push(ev.view.kind);
        ctrl.abort();
      }
    } catch {
      /* aborted */
    }
    expect(seen.length).toBeGreaterThanOrEqual(1);
  });

  it("refuses a conversation with an assistant the person lacks", async () => {
    await expect(clientAs("employee").conversations.create("investigation-triage", "k9")).rejects.toBeInstanceOf(ForbiddenError);
  });
});
