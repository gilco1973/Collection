/** Fail-first tests for the round-2 frontend findings. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18next from "i18next";
import Markdown from "../components/Markdown";
import { formatDate, formatMoney } from "../format";
import App from "../App";
import AuditDetail from "../pages/AuditDetail";
import Audits from "../pages/Audits";
import Home from "../pages/Home";
import RunAudit from "../pages/RunAudit";
import Search from "../pages/Search";
import { audit, defaultResponder, mockFetch, renderAt, summary } from "./harness";

afterEach(() => vi.unstubAllGlobals());

describe("Markdown renderer", () => {
  it("terminates on hash lines that are not headings", () => {
    const started = Date.now();
    render(<Markdown source={"intro\n#123 is an issue ref\n#!/bin/sh\nend"} basePath="index.md" />);
    expect(Date.now() - started).toBeLessThan(2000);
    expect(screen.getByText(/#123 is an issue ref/)).toBeInTheDocument();
  });

  it("demotes body H1s, renders italics and alignment tables, and keeps unsafe schemes inert", () => {
    render(<Markdown source={"# One\n\n*it* and [j](javascript:alert(1)) and [m](mailto:a@b.c)\n\n| a | b |\n|:--|--:|\n| 1 | 2 |"} basePath="index.md" />);
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "One" })).toBeInTheDocument();
    expect(screen.getByText("it").tagName).toBe("EM");
    expect(screen.queryByRole("link", { name: "j" })).toBeNull();
    expect(screen.getByRole("link", { name: "m" })).toHaveAttribute("href", "mailto:a@b.c");
    expect(screen.queryByText(":--")).toBeNull();
  });
});

describe("plurals and locale formatting", () => {
  it("uses singular and plural forms", () => {
    expect(i18next.t("search.results", { count: 1 })).toBe("1 result");
    expect(i18next.t("search.results", { count: 2 })).toBe("2 results");
    expect(i18next.t("home.findings", { count: 1 })).toBe("1 finding");
  });
  it("formats dates and money per locale", () => {
    expect(formatMoney(0.5, "en")).toBe("$0.50");
    expect(formatMoney(0.5, "fr")).toMatch(/0,50/);
    expect(formatDate("2026-09-15T10:00:00Z", "en")).toMatch(/2026/);
  });
});

describe("route state and titles", () => {
  it("sets the document title from the page", async () => {
    mockFetch(defaultResponder());
    render(<App />, { wrapper: ({ children }) => <>{children}</> });
    await waitFor(() => expect(document.title).toBe("Start here · KnowledgeBase Console"));
  });

  it("keys audit detail by id so polling follows the audit shown", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1": audit({ status: "in_progress" }) }));
    renderAt("/audits/audit-1?tab=summary", <AuditDetail />, undefined, "/audits/:id");
    expect(await screen.findByRole("tab", { name: "Summary", selected: true })).toBeInTheDocument();
  });
});

describe("tabs and dialog accessibility", () => {
  it("moves between tabs with arrow keys and reflects the tab in the URL", async () => {
    mockFetch(defaultResponder());
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    const first = await screen.findByRole("tab", { name: "Findings" });
    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Actions" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Actions" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby");
  });

  it("focuses the reason field when the live dialog opens and closes on Escape", async () => {
    mockFetch(defaultResponder());
    renderAt("/audits/new", <RunAudit />, undefined, "/audits/new");
    await userEvent.click(await screen.findByRole("radio", { name: /LIVE/ }));
    await userEvent.click(screen.getByRole("button", { name: "Start LIVE audit" }));
    expect(screen.getByLabelText("Reason")).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});

describe("cancel, search and audits list", () => {
  it("confirms before cancelling and shows a cancel error", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1": audit({ status: "in_progress" }), "/audits/audit-1/cancel": new Response(JSON.stringify({ error: { code: "http_error", message: "audit is completed", request_id: "r" } }), { status: 409 }) }));
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    await userEvent.click(await screen.findByRole("button", { name: "Cancel audit" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    expect(await screen.findByText("audit is completed")).toBeInTheDocument();
  });

  it("replaces history while typing and keeps the selected facet", async () => {
    const calls = mockFetch(defaultResponder({ "/search": { items: [], total: 0, facets: { section: [], status: [], owner: [], audience: [] } } }));
    renderAt("/search?owner=risk", <Search />, undefined, "/search");
    expect(await screen.findByDisplayValue("risk")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText("Search pages…"), "gate");
    await waitFor(() => expect(calls.filter((c) => c.path.includes("q=gate")).length).toBe(1), { timeout: 2000 });
    expect(calls.some((c) => c.path.includes("q=g&"))).toBe(false);
  });

  it("paginates the audits list", async () => {
    mockFetch(defaultResponder({ "/audits": { items: [summary()], total: 60 } }));
    renderAt("/audits", <Audits />);
    expect(await screen.findByRole("button", { name: "Next page" })).toBeEnabled();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
  });

  it("hides the run CTA from viewers and links the first section", async () => {
    mockFetch(defaultResponder({ "/me": { role: "viewer", live_allowed: false, atlassian_configured: false } }));
    renderAt("/", <Home />);
    await waitFor(() => expect(screen.getByRole("link", { name: "Start reading" })).toHaveAttribute("href", "/kb/onboarding"));
    expect(screen.queryByRole("link", { name: "Run an audit" })).toBeNull();
  });
});
