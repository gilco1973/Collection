/** Page-level coverage: the single router, keyed routes, retry handlers, pagination, Atlassian gating, unsaved key state. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App, { AppRoutes } from "../App";
import Audits from "../pages/Audits";
import Browse from "../pages/Browse";
import Home from "../pages/Home";
import PageView from "../pages/PageView";
import RunAudit from "../pages/RunAudit";
import Search from "../pages/Search";
import Settings from "../pages/Settings";
import { contract, defaultResponder, errorResponse, mockFetch, renderAt, summary } from "./harness";

afterEach(() => vi.unstubAllGlobals());

const renderApp = (path: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>
    </QueryClientProvider>,
  );

describe("single router", () => {
  it("routes by pathname under BASE_URL; links carry paths, not hash fragments", async () => {
    mockFetch(defaultResponder());
    window.history.replaceState({}, "", "/");
    render(<App />);
    await waitFor(() => expect(screen.getByRole("link", { name: "Start reading" })).toHaveAttribute("href", "/kb/onboarding"));
    expect(window.location.hash).toBe("");
  });
});

describe("keyed routes", () => {
  it("mounts each keyed page and moves focus to main after navigation", async () => {
    mockFetch(defaultResponder());
    renderApp("/kb/onboarding");
    expect(await screen.findByRole("link", { name: "Stale" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Stale" }));
    await waitFor(() => expect(document.title).toBe("Onboarding · KnowledgeBase Console"));
    expect(document.getElementById("main")).toHaveFocus();
    renderApp("/audits/audit-1/actions/act-1/rollback");
    expect(await screen.findByRole("heading", { name: /Roll back an action/ })).toBeInTheDocument();
    renderApp("/audits/audit-1");
    expect((await screen.findAllByRole("heading", { name: "audit-1" })).length).toBe(1);
  });
});

describe("retry handlers", () => {
  it("refetches from every error box", async () => {
    const calls = mockFetch(defaultResponder({ "/sections": errorResponse(500, "s"), "/pages": errorResponse(500, "p"), "/audits": errorResponse(500, "a") }));
    renderAt("/", <Home />);
    const buttons = await screen.findAllByRole("button", { name: "Retry" });
    expect(buttons.length).toBe(3);
    const before = calls.length;
    for (const b of buttons) await userEvent.click(b);
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(before + 3));
  });

  it("retries browse, page, findings and search errors", async () => {
    mockFetch(defaultResponder({ "/sections": errorResponse(500, "s"), "/sections/onboarding/pages": errorResponse(500, "sp") }));
    renderAt("/kb/onboarding", <Browse />, undefined, "/kb/:section");
    await userEvent.click((await screen.findAllByRole("button", { name: "Retry" }))[0]);
    cleanup();
    mockFetch(defaultResponder({ "/pages/onboarding/README.md/findings": errorResponse(500, "f") }));
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    cleanup();
    mockFetch(defaultResponder({ "/search": errorResponse(500, "q") }));
    renderAt("/search?q=x", <Search />);
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("q")).toBeInTheDocument();
  });
});

describe("audits pagination", () => {
  it("moves to the next page and back", async () => {
    const calls = mockFetch(defaultResponder({ "/audits": { items: [summary()], total: 45 } }));
    renderAt("/audits", <Audits />);
    await userEvent.click(await screen.findByRole("button", { name: "Next page" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("page=2"))).toBe(true));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Type"), "offline");
    await waitFor(() => expect(calls.some((c) => c.path.includes("type=offline"))).toBe(true));
  });
});

describe("run audit gating", () => {
  it("locks Atlassian capabilities and sends no capabilities for offline runs", async () => {
    const calls = mockFetch(defaultResponder({ "/contract": { ...contract, capabilities: [...contract.capabilities, "atlassian"] }, "/audits": { audit_id: "audit-9", dry_run: true, forced_dry_run: false } }));
    renderAt("/audits/new", <RunAudit />, undefined, "/audits/new");
    expect(await screen.findByLabelText(/atlassian/)).toBeDisabled();
    expect(screen.getByLabelText("links")).toBeChecked();
    await userEvent.click(screen.getByLabelText("Deterministic checks only"));
    await userEvent.click(screen.getByLabelText(/Verify external links/));
    await userEvent.click(screen.getByRole("button", { name: "Start dry run" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
    const post = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ type: "offline", network: true });
    expect(JSON.parse(String(post?.init?.body)).capabilities).toBeUndefined();
  });

  it("shows the identity error with a retry", async () => {
    mockFetch(defaultResponder({ "/me": errorResponse(500, "identity down") }));
    renderAt("/audits/new", <RunAudit />, undefined, "/audits/new");
    expect(await screen.findByText("identity down")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  });
});

describe("settings key state", () => {
  it("flags unsaved edits and clears the key", async () => {
    mockFetch(defaultResponder({ "/contract": errorResponse(500, "no contract") }));
    renderAt("/settings", <Settings />);
    await userEvent.type(await screen.findByLabelText("Operator key"), "zzz");
    expect(screen.getByText("Not saved yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText("Not saved yet.")).toBeNull();
    expect(await screen.findByText("Yes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  });
});
