import { describe, expect, it, vi } from "vitest";
import { ApiClient, type Transport } from "./client";
import { ConflictError, NetworkError, ServerError, UnauthorizedError, ValidationError, errorFromResponse, isTransient } from "./errors";

const problem = (status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify({ status, ...body }), { status, headers: { "Content-Type": "application/problem+json", "X-Request-Id": "srv-1" } });

function clientWith(transport: Transport, token: string | undefined = "tok", onUnauthorized?: () => void) {
  return new ApiClient("/api", transport, async () => token, { onUnauthorized });
}

describe("ApiClient", () => {
  it("sends the bearer token, request id, traceparent and build header", async () => {
    const seen: Request[] = [];
    const t: Transport = async (req) => {
      seen.push(req);
      return Response.json({ ok: true });
    };
    await clientWith(t).get("/me");
    const req = seen[0];
    expect(req.url).toMatch(/\/api\/me$/);
    expect(req.headers.get("authorization")).toBe("Bearer tok");
    expect(req.headers.get("x-request-id")).toMatch(/^[0-9a-f]{32}$/);
    expect(req.headers.get("traceparent")).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
    expect(req.headers.get("x-client-build")).toBeTruthy();
  });

  it("carries Idempotency-Key and If-Match when given", async () => {
    const seen: Request[] = [];
    const t: Transport = async (req) => {
      seen.push(req);
      return Response.json({});
    };
    await clientWith(t).patch("/briefs/b1", { a: 1 }, { ifMatch: 'W/"3"', idempotencyKey: "k1" });
    expect(seen[0].headers.get("if-match")).toBe('W/"3"');
    expect(seen[0].headers.get("idempotency-key")).toBe("k1");
    expect(seen[0].headers.get("content-type")).toBe("application/json");
  });

  it("maps problem+json to typed errors and keeps the server's request id", async () => {
    const t: Transport = async () => problem(409, { title: "Changed elsewhere", detail: "Reload." });
    const err = (await clientWith(t)
      .get("/x")
      .catch((e: unknown) => e)) as ConflictError;
    expect(err).toBeInstanceOf(ConflictError);
    expect(err.message).toBe("Reload.");
    expect(err.requestId).toBe("srv-1");
    expect(err.supportLine).toContain("HTTP 409");
  });

  it("exposes field errors on 422", async () => {
    const t: Transport = async () => problem(422, { title: "Invalid", errors: { "useCase.name": ["Give the use case a name."] } });
    const err = (await clientWith(t)
      .post("/briefs/b1/file")
      .catch((e: unknown) => e)) as ValidationError;
    expect(err).toBeInstanceOf(ValidationError);
    expect(err.fieldErrors["useCase.name"]).toEqual(["Give the use case a name."]);
  });

  it("calls the unauthorized hook on 401", async () => {
    const hook = vi.fn();
    const t: Transport = async () => problem(401, { title: "Unauthenticated" });
    await expect(clientWith(t, "tok", hook).get("/me")).rejects.toBeInstanceOf(UnauthorizedError);
    expect(hook).toHaveBeenCalledTimes(1);
  });

  it("retries an idempotent request once on a transient failure, never a mutation", async () => {
    let n = 0;
    const flaky: Transport = async () => (++n === 1 ? problem(503, { title: "Busy" }) : Response.json({ ok: true }));
    await expect(clientWith(flaky).get("/catalog")).resolves.toEqual({ ok: true });
    expect(n).toBe(2);
    n = 0;
    await expect(clientWith(flaky).post("/briefs", {})).rejects.toBeInstanceOf(ServerError);
    expect(n).toBe(1);
  });

  it("wraps a transport failure as NetworkError", async () => {
    const t: Transport = async () => {
      throw new TypeError("Failed to fetch");
    };
    await expect(clientWith(t).post("/x", {})).rejects.toBeInstanceOf(NetworkError);
  });

  it("returns undefined for 204", async () => {
    const t: Transport = async () => new Response(null, { status: 204 });
    await expect(clientWith(t).post("/conversations/c/feedback", {})).resolves.toBeUndefined();
  });
});

describe("errors", () => {
  it("classifies transient failures", () => {
    expect(isTransient(new NetworkError(new Error("x")))).toBe(true);
    expect(isTransient(errorFromResponse(503, undefined, undefined))).toBe(true);
    expect(isTransient(errorFromResponse(500, undefined, undefined))).toBe(false);
    expect(isTransient(errorFromResponse(404, undefined, undefined))).toBe(false);
  });
});
