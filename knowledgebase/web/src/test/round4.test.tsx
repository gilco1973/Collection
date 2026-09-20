/** Round-4 findings: focus is not stolen on load; polling continues; the link regex splits deterministically. */
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, afterEach } from "vitest";
import AuditDetail from "../pages/AuditDetail";
import { TOKEN } from "../components/markdownInline";
import { audit, defaultResponder, mockFetch, renderAt } from "./harness";

afterEach(() => vi.unstubAllGlobals());

describe("audit header focus", () => {
  it("does not move focus to the cancel button when the page loads", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1": audit({ status: "in_progress" }) }));
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    const cancel = await screen.findByRole("button", { name: "Cancel audit" });
    expect(cancel).not.toHaveFocus();
  });

  it("keeps polling a running audit", async () => {
    const calls = mockFetch(defaultResponder({ "/audits/audit-1": audit({ status: "in_progress" }) }));
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    await screen.findByRole("heading", { name: "audit-1" });
    await waitFor(() => expect(calls.filter((c) => c.path === "/audits/audit-1").length).toBeGreaterThanOrEqual(2), { timeout: 5000 });
  }, 7000);
});

describe("inline link token", () => {
  it("never matches an unclosed link and matches one balanced parenthesised segment", () => {
    TOKEN.lastIndex = 0;
    expect(TOKEN.exec(`[x](${"a".repeat(50_000)}`)).toBeNull();
    TOKEN.lastIndex = 0;
    expect(TOKEN.exec("[w](https://x.example/Foo_(bar)_baz)")?.[7]).toBe("https://x.example/Foo_(bar)_baz");
  });
});
