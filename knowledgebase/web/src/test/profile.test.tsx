import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import Browse from "../pages/Browse";
import Home from "../pages/Home";
import PageView from "../pages/PageView";
import Settings from "../pages/Settings";
import { defaultResponder, mockFetch, profile, renderAt, signedIn, viewer } from "./harness";

const signedInWithProfile = (extra: Record<string, unknown> = {}) =>
  defaultResponder({ "/me": signedIn, "/profile": profile, "/profile/views": { path: "onboarding/README.md", count: 3 }, ...extra });

describe("Reading progress", () => {
  it("records a page view once for a signed-in reader", async () => {
    const calls = mockFetch(signedInWithProfile());
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    await screen.findByRole("heading", { level: 1, name: "Onboarding" });
    await waitFor(() => expect(calls.filter((c) => c.path === "/profile/views").length).toBe(1));
    expect(JSON.parse(String(calls.find((c) => c.path === "/profile/views")?.init?.body))).toEqual({ path: "onboarding/README.md" });
  });

  it("never records a view for an anonymous reader", async () => {
    const calls = mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    await screen.findByRole("heading", { level: 1, name: "Onboarding" });
    expect(calls.some((c) => c.path === "/profile/views" || c.path === "/profile")).toBe(false);
  });

  it("marks read pages and section progress in Browse", async () => {
    mockFetch(signedInWithProfile());
    renderAt("/kb/onboarding", <Browse />, undefined, "/kb/:section");
    expect(await screen.findByText("Read")).toBeInTheDocument();
    expect(screen.getByTestId("progress-onboarding")).toHaveTextContent("1/2");
    expect(screen.queryByTestId("progress-governance")).toHaveTextContent("0/1");
  });

  it("offers to continue reading on Home with section progress", async () => {
    mockFetch(signedInWithProfile());
    renderAt("/", <Home />);
    const list = await screen.findByTestId("continue-reading");
    expect(list).toHaveTextContent("Onboarding");
    expect(screen.getByText(/1 of 2 read/)).toBeInTheDocument();
  });

  it("hides the continue-reading card when nothing was read", async () => {
    mockFetch(signedInWithProfile({ "/profile": { ...profile, viewed: {} } }));
    renderAt("/", <Home />);
    await screen.findByText("Start here");
    expect(screen.queryByTestId("continue-reading")).toBeNull();
  });

  it("deletes the reader's data from Settings after a confirmation step", async () => {
    const calls = mockFetch(signedInWithProfile({ "/profile": new Response(null, { status: 204 }) }));
    renderAt("/settings", <Settings />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
    expect(calls.some((c) => c.init?.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete my data" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete everything" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/profile" && c.init?.method === "DELETE")).toBe(true));
    expect(await screen.findByText("Deleted.")).toBeInTheDocument();
  });
});
