/** Round-3 findings: state reset per entity, focus management, inline Escape, RTL keys, regex bound, debounce race. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppRoutes } from "../App";
import Tabs from "../components/Tabs";
import AuditDetail from "../pages/AuditDetail";
import Rollback from "../pages/Rollback";
import RunAudit from "../pages/RunAudit";
import Search from "../pages/Search";
import { audit, defaultResponder, detail, mockFetch, renderAt } from "./harness";

afterEach(() => vi.unstubAllGlobals());

const app = (path: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>
    </QueryClientProvider>,
  );

describe("state is scoped to the entity shown", () => {
  it("forgets a sent problem report when another page opens", async () => {
    const other = { ...detail, meta: { ...detail.meta, path: "onboarding/day-one.md", title: "Day one" }, body_markdown: "# Day one\n\nBack to [Onboarding](README.md)." };
    mockFetch(defaultResponder({ "/pages/onboarding/README.md/reports": { id: "p", owner: "e" }, "/pages/onboarding/day-one.md": other, "/pages/onboarding/day-one.md/findings": { items: [] } }));
    app("/kb/page/onboarding/day-one.md");
    await userEvent.type(await screen.findByLabelText("Tell the owner what you found"), "This page is out of date.");
    mockFetch(defaultResponder({ "/pages/onboarding/day-one.md/reports": { id: "p", owner: "e" }, "/pages/onboarding/day-one.md": other, "/pages/onboarding/day-one.md/findings": { items: [] } }));
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("status")).toHaveFocus();
    const back = screen.getAllByRole("link", { name: "Onboarding" }).find((l) => l.getAttribute("href") === "/kb/page/onboarding/README.md")!;
    await userEvent.click(back);
    expect(await screen.findByLabelText("Tell the owner what you found")).toHaveValue("");
  });

  it("polls the audit that is shown after the id changes", async () => {
    const calls = mockFetch(defaultResponder({ "/audits/audit-2": audit({ audit_id: "audit-2", status: "in_progress" }) }));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
        <MemoryRouter initialEntries={["/audits/audit-1"]}>
          <Routes><Route path="/audits/:id" element={<><Link to="/audits/audit-2">next audit</Link><AuditDetail /></>} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "audit-1" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "next audit" }));
    expect(await screen.findByRole("heading", { name: "audit-2" })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.path === "/audits/audit-2")).toBe(true));
  });
});

describe("focus and keyboard", () => {
  it("moves focus into the cancel confirmation and back to the trigger", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1": audit({ status: "in_progress" }) }));
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    await userEvent.click(await screen.findByRole("button", { name: "Cancel audit" }));
    expect(screen.getByRole("button", { name: "Confirm cancel" })).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "Keep running" }));
    expect(screen.getByRole("button", { name: "Cancel audit" })).toHaveFocus();
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute("href", expect.stringContaining("format=json"));
  });

  it("keeps the rollback reason when Escape is pressed in the inline dialog", async () => {
    mockFetch(defaultResponder());
    renderAt("/audits/audit-1/actions/act-1/rollback", <Rollback />, undefined, "/audits/:id/actions/:actionId/rollback");
    const reason = await screen.findByLabelText("Reason");
    await userEvent.type(reason, "undo it{Escape}");
    expect(screen.getByLabelText("Reason")).toHaveValue("undo it");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("act-1");
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("mirrors arrow keys in RTL", async () => {
    const onChange = vi.fn();
    render(<div dir="rtl" style={{ direction: "rtl" }}><Tabs tabs={[{ key: "a", label: "A" }, { key: "b", label: "B" }]} current="a" label="d" onChange={onChange}><p>x</p></Tabs></div>);
    screen.getByRole("tab", { name: "A" }).focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("b");
    expect(screen.getByRole("tabpanel").className).toContain("focus-visible:ring-2");
  });
});

describe("search debounce", () => {
  it("keeps a facet chosen inside the debounce window", async () => {
    const calls = mockFetch(defaultResponder());
    renderAt("/search", <Search />);
    await userEvent.type(await screen.findByPlaceholderText("Search pages…"), "gate");
    await userEvent.selectOptions(screen.getByLabelText("Section"), "onboarding");
    await waitFor(() => expect(calls.some((c) => c.path.includes("q=gate") && c.path.includes("section=onboarding"))).toBe(true), { timeout: 2000 });
    await new Promise((r) => setTimeout(r, 400));
    expect(calls.filter((c) => c.path.includes("q=gate") && !c.path.includes("section=onboarding")).length).toBe(0);
  });
});

describe("run form", () => {
  it("requires a capability, caps the budget at the server ceiling and opens the summary tab", async () => {
    const calls = mockFetch(defaultResponder({ "/audits": { audit_id: "audit-9", dry_run: true, forced_dry_run: false } }));
    renderAt("/audits/new", <RunAudit />, <Route path="/audits/:id" element={<div>detail-page</div>} />, "/audits/new");
    for (const c of ["frontmatter", "links", "structure"]) await userEvent.click(await screen.findByLabelText(c));
    expect(screen.getByRole("button", { name: "Start dry run" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose at least one capability.");
    expect(screen.getByLabelText("Budget (USD)")).toHaveAttribute("max", "2");
    await userEvent.click(screen.getByLabelText("links"));
    await userEvent.click(screen.getByRole("button", { name: "Start dry run" }));
    expect(await screen.findByText("detail-page")).toBeInTheDocument();
    expect(calls.some((c) => c.init?.method === "POST")).toBe(true);
  });
});
