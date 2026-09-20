import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import Home from "../pages/Home";
import Settings from "../pages/Settings";
import { defaultResponder, mockFetch, renderAt, signedIn, viewer } from "./harness";

describe("Identity", () => {
  it("shows nothing on a server without single sign-on", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/kb", <Home />);
    expect(await screen.findByText("Start here")).toBeInTheDocument();
    expect(screen.queryByTestId("sign-in")).toBeNull();
    expect(screen.queryByRole("button", { name: /Sign out/ })).toBeNull();
  });

  it("offers sign-in that returns to the current page", async () => {
    mockFetch(defaultResponder({ "/me": { ...viewer, sso_configured: true } }));
    renderAt({ pathname: "/kb", search: "?x=1" }, <Home />);
    const link = await screen.findByTestId("sign-in");
    expect(link).toHaveTextContent("Sign in");
    expect(link).toHaveAttribute("href", "/api/auth/login?next=%2Fkb%3Fx%3D1");
  });

  it("shows the signed-in name and signs out with a POST", async () => {
    const calls = mockFetch(defaultResponder({ "/me": signedIn, "/auth/logout": new Response(null, { status: 204 }) }));
    renderAt("/", <Home />);
    expect(await screen.findByTestId("signed-in-name")).toHaveTextContent("Ada Lovelace");
    await userEvent.click(screen.getByRole("button", { name: "Sign out (Ada Lovelace)" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/auth/logout" && c.init?.method === "POST")).toBe(true));
    await waitFor(() => expect(calls.filter((c) => c.path === "/me").length).toBeGreaterThan(1)); // "me" refetched after sign-out
  });

  it("settings shows who is signed in", async () => {
    mockFetch(defaultResponder({ "/me": signedIn }));
    renderAt("/settings", <Settings />);
    expect(await screen.findByTestId("settings-user")).toHaveTextContent("Signed in as Ada Lovelace");
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("settings offers sign-in when nobody is signed in", async () => {
    mockFetch(defaultResponder({ "/me": { ...viewer, sso_configured: true } }));
    renderAt("/settings", <Settings />);
    const links = await screen.findAllByRole("link", { name: "Sign in" });
    expect(links.at(-1)).toHaveAttribute("href", "/api/auth/login?next=%2Fsettings");
  });

  it("settings explains when single sign-on is not configured", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/settings", <Settings />);
    expect(await screen.findByText("Single sign-on is not configured on this server.")).toBeInTheDocument();
  });
});
