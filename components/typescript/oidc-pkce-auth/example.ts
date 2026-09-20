// Live example: the persona client and the permits set, in Node (a tiny sessionStorage shim stands in for the browser). Run: npx tsx example.ts
const store = new Map<string, string>();
(globalThis as { window?: unknown }).window = { sessionStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v), removeItem: (k: string) => store.delete(k) }, location: { href: "http://localhost/" } };
const { createMockClient } = await import("./src/mock");
const { permits, primaryRole } = await import("./src/permits");
const { PRINCIPALS } = await import("./src/fixtures");

const client = createMockClient();
console.log("before sign-in:", await client.initialize());
const snap = await client.signIn({ persona: "gk" });
console.log("after sign-in:", snap?.status, "| bearer:", await client.getAccessToken());
const me = PRINCIPALS[(await client.getAccessToken())!.slice(5)];   // what GET /me would return for that bearer
console.log("principal:", me.name, "| primary role:", primaryRole(me), "| ladder:", me.ladder);
for (const [action, resource] of [["hub.workspace", {}], ["consumer.open", { consumerId: "investigation-triage" }], ["consumer.open", { consumerId: "payments-exception-agent" }], ["brief.file", {}], ["admin.manage", {}]] as const) {
  console.log(`  can ${action}${"consumerId" in resource ? " " + resource.consumerId : ""}:`, permits(me, action, resource));
}
await client.signOut();
console.log("after sign-out:", await client.initialize());
