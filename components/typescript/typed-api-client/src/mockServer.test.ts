import { describe, expect, it } from "vitest";
import { ApiClient } from "./client";
import { NotFoundError, UnauthorizedError, ValidationError } from "./errors";
import { createMockServer, json, problem } from "./mockServer";

const server = createMockServer<{ id: string }>((token) => (token?.startsWith("mock.") ? { id: token.slice(5) } : undefined));
server.route("GET", "/me", ({ principal }) => json(principal));
server.route("GET", "/items/:id", ({ params }) => (params.id === "missing" ? problem(404, { title: "Not found" }) : json({ id: params.id })));
server.route("POST", "/items", ({ body }) => ((body as { name?: string }).name ? json({ id: "new", ...(body as object) }, { status: 201 }) : problem(422, { title: "Invalid", errors: { name: ["Give it a name."] } })));
server.route("GET", "/health", () => json({ ok: true }), { anonymous: true });

const client = (token?: string) => new ApiClient("/api", server.serve, async () => token);

describe("mock server as a transport", () => {
  it("resolves the bearer to a principal and refuses without one", async () => {
    await expect(client("mock.gk").get("/me")).resolves.toEqual({ id: "gk" });
    await expect(client(undefined).get("/me")).rejects.toBeInstanceOf(UnauthorizedError);
    await expect(client(undefined).get("/health")).resolves.toEqual({ ok: true });
  });

  it("maps route params and problems", async () => {
    await expect(client("mock.gk").get("/items/a%20b")).resolves.toEqual({ id: "a b" });
    await expect(client("mock.gk").get("/items/missing")).rejects.toBeInstanceOf(NotFoundError);
    await expect(client("mock.gk").get("/nowhere")).rejects.toBeInstanceOf(NotFoundError);
    const err = (await client("mock.gk").post("/items", {}).catch((e: unknown) => e)) as ValidationError;
    expect(err.fieldErrors.name).toEqual(["Give it a name."]);
  });

  it("replays the first response for a repeated idempotency key", async () => {
    const c = client("mock.gk");
    const a = await c.post<{ id: string }>("/items", { name: "x" }, { idempotencyKey: "k1" });
    const b = await c.post<{ id: string }>("/items", { name: "y" }, { idempotencyKey: "k1" });
    expect(b).toEqual(a);
    server.reset();
    await expect(c.post("/items", { name: "y" }, { idempotencyKey: "k1" })).resolves.toMatchObject({ name: "y" });
  });
});
