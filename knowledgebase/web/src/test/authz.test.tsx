import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import Settings from "../pages/Settings";
import { defaultResponder, me, mockFetch, renderAt, signedIn } from "./harness";

const HELP = "Ends your sessions in every browser and on every device; sign in again to continue.";
const groupOperator = {
  ...signedIn,
  role: "operator",
  operator_via: "group",
  user: { sub: "u-1", name: "Ada Lovelace", email: "ada@example.com", operator: true },
};

describe("Authorisation in Settings", () => {
  it("offers sign out everywhere with its help text and posts it, then refetches me", async () => {
    const calls = mockFetch(defaultResponder({ "/me": signedIn, "/auth/logout-everywhere": new Response(null, { status: 204 }) }));
    renderAt("/settings", <Settings />);
    expect(await screen.findByText(HELP)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/auth/logout-everywhere" && c.init?.method === "POST")).toBe(true));
    await waitFor(() => expect(calls.filter((c) => c.path === "/me").length).toBeGreaterThan(1));
  });

  it("does not offer sign out everywhere to an anonymous reader", async () => {
    mockFetch(defaultResponder({ "/me": { ...signedIn, user: null } }));
    renderAt("/settings", <Settings />);
    expect(await screen.findAllByRole("link", { name: "Sign in" })).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Sign out everywhere" })).toBeNull();
    expect(screen.queryByText(HELP)).toBeNull();
  });

  it("says the operator role came from the identity provider group", async () => {
    mockFetch(defaultResponder({ "/me": groupOperator }));
    renderAt("/settings", <Settings />);
    expect(await screen.findByTestId("settings-role")).toHaveTextContent("Operator · via your identity provider group");
  });

  it("says the operator role came from the operator key", async () => {
    mockFetch(defaultResponder({ "/me": me }));
    renderAt("/settings", <Settings />);
    expect(await screen.findByTestId("settings-role")).toHaveTextContent("Operator · via the operator key");
  });

  it("shows a plain role for a viewer", async () => {
    mockFetch(defaultResponder({ "/me": signedIn }));
    renderAt("/settings", <Settings />);
    expect(await screen.findByTestId("settings-role")).toHaveTextContent(/^Viewer$/);
  });
});
