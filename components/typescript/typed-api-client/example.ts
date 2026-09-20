// Live example: the real client against the in-process mock server. Run: npx tsx example.ts
import { ApiClient, createMockServer, json, problem } from "./src";
import { ConflictError, ValidationError } from "./src/errors";

const server = createMockServer<{ id: string; role: string }>((token) => (token === "mock.gk" ? { id: "gk", role: "ops.lead" } : undefined));
server.route("GET", "/me", ({ principal }) => json(principal));
server.route("PATCH", "/briefs/:id", ({ params, req, body }) =>
  req.headers.get("if-match") === 'W/"3"' ? json({ id: params.id, etag: 'W/"4"', ...(body as object) }) : problem(409, { title: "Changed elsewhere", detail: "Reload and try again." }),
);
server.route("POST", "/briefs", ({ body }) => ((body as { name?: string }).name ? json({ id: "brf_1", ...(body as object) }, { status: 201 }) : problem(422, { title: "Invalid", errors: { name: ["Give the brief a name."] } })));

const api = new ApiClient("/api", server.serve, async () => "mock.gk", { buildSha: "example", onUnauthorized: () => console.log("signed out") });
console.log("GET /me ->", await api.get("/me"));
console.log("PATCH with the right etag ->", await api.patch("/briefs/b1", { step: "model" }, { ifMatch: 'W/"3"' }));
try { await api.patch("/briefs/b1", { step: "model" }, { ifMatch: 'W/"2"' }); } catch (e) { console.log("stale etag ->", (e as ConflictError).name, "|", (e as ConflictError).supportLine); }
try { await api.post("/briefs", {}, { idempotencyKey: "k1" }); } catch (e) { console.log("invalid body ->", (e as ValidationError).name, (e as ValidationError).fieldErrors); }
const a = await api.post("/briefs", { name: "Runbook answers" }, { idempotencyKey: "k2" });
const b = await api.post("/briefs", { name: "changed" }, { idempotencyKey: "k2" });
console.log("same idempotency key twice -> same response:", JSON.stringify(a) === JSON.stringify(b));
