import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route } from "react-router-dom";
import Audits from "../pages/Audits";
import Browse from "../pages/Browse";
import Home from "../pages/Home";
import Search from "../pages/Search";
import Settings from "../pages/Settings";
import { setContentLanguage } from "../contentLanguage";
import { defaultResponder, errorResponse, mockFetch, page, renderAt, sections, viewer } from "./harness";

afterEach(() => {
  vi.unstubAllGlobals();
  setContentLanguage("en");
});

describe("Home", () => {
  it("shows the latest audit, stale pages and sections", async () => {
    mockFetch(defaultResponder());
    renderAt("/", <Home />);
    expect(await screen.findByText("audit-1")).toBeInTheDocument();
    expect(screen.getByText("2 findings · 1 for human review")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Stale" })).toBeInTheDocument();
    expect(await screen.findByText("Onboarding")).toBeInTheDocument();
    expect(screen.getByText("2 pages · 1 stale")).toBeInTheDocument();
    expect(screen.getByTestId("role")).toHaveTextContent("Operator");
  });

  it("shows empty and error states", async () => {
    mockFetch(defaultResponder({ "/audits": { items: [], total: 0 }, "/pages": { items: [] }, "/sections": errorResponse(500, "db down") }));
    renderAt("/", <Home />);
    expect(await screen.findByText("No audits yet.")).toBeInTheDocument();
    expect(await screen.findByText("Every page is within its review window.")).toBeInTheDocument();
    expect(await screen.findByText("db down")).toBeInTheDocument();
    expect(screen.getByText("Request id req-1")).toBeInTheDocument();
  });

  it("re-fetches sections and stale pages in the selected content language", async () => {
    mockFetch(
      defaultResponder({
        "/sections?lang=es": sections.map((s) => (s.id === "onboarding" ? { ...s, title: "Incorporación" } : s)),
        "/pages?stale=true&lang=es": { items: [page({ path: "onboarding/stale.md", title: "Página obsoleta", stale: true })] },
      }),
    );
    renderAt("/", <Home />);
    expect(await screen.findByText("Onboarding")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Content language"), "es");
    expect(await screen.findByText("Incorporación")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Página obsoleta" })).toBeInTheDocument();
  });
});

describe("Browse", () => {
  it("lists sections and pages with stale markers", async () => {
    mockFetch(defaultResponder());
    renderAt("/kb/onboarding", <Browse />, undefined, "/kb/:section");
    expect(await screen.findByRole("link", { name: "Stale" })).toBeInTheDocument();
    expect(screen.getByText("Owner: enablement · Review window: 90 days")).toBeInTheDocument();
    expect(screen.getAllByText("Stale").length).toBeGreaterThan(1);
  });

  it("shows the empty state without a section", async () => {
    mockFetch(defaultResponder());
    renderAt("/kb", <Browse />);
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
  });

  it("re-fetches the section list and its pages in the selected content language", async () => {
    mockFetch(
      defaultResponder({
        "/sections?lang=es": sections.map((s) => (s.id === "onboarding" ? { ...s, title: "Incorporación" } : s)),
        "/sections/onboarding/pages?lang=es": { items: [page({ title: "Inicio" })] },
      }),
    );
    renderAt("/kb/onboarding", <Browse />, undefined, "/kb/:section");
    expect(await screen.findByRole("link", { name: "Stale" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Content language"), "es");
    expect((await screen.findAllByText("Incorporación")).length).toBeGreaterThan(0); // section nav item + card title
    expect(await screen.findByRole("link", { name: "Inicio" })).toBeInTheDocument();
  });
});

describe("Search", () => {
  it("searches, filters and shows results", async () => {
    const calls = mockFetch(defaultResponder());
    renderAt("/search?q=hello", <Search />);
    expect(await screen.findByText("1 result")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Section"), "onboarding");
    await userEvent.click(screen.getByLabelText("Stale only"));
    await waitFor(() => expect(calls.some((c) => c.path.includes("section=onboarding") && c.path.includes("stale=true"))).toBe(true));
    await userEvent.clear(screen.getByPlaceholderText("Search pages…"));
    await waitFor(() => expect(calls.some((c) => c.path.includes("section=onboarding") && !c.path.includes("q="))).toBe(true), { timeout: 2000 });
  });

  it("shows no results", async () => {
    mockFetch(defaultResponder({ "/search": { items: [], total: 0, facets: {} } }));
    renderAt("/search", <Search />);
    expect(await screen.findByText("No pages match.")).toBeInTheDocument();
  });

  it("passes the selected content language to search", async () => {
    mockFetch(
      defaultResponder({
        "/search?lang=es": {
          items: [{ ...page(), title: "Resultado", snippet: "hola" }],
          total: 1,
          facets: { section: [], status: [], audience: [], owner: [] },
        },
      }),
    );
    renderAt("/search", <Search />);
    expect(await screen.findByText("Onboarding")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Content language"), "es");
    expect(await screen.findByText("Resultado")).toBeInTheDocument();
  });
});

describe("Audits list", () => {
  it("lists audits and filters by mode", async () => {
    const calls = mockFetch(defaultResponder());
    renderAt("/audits", <Audits />);
    expect(await screen.findByRole("link", { name: "audit-1" })).toBeInTheDocument();
    expect(screen.getAllByText("DRY RUN").length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText("Mode"), "live");
    await waitFor(() => expect(calls.some((c) => c.path.includes("mode=live"))).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    await waitFor(() => expect(calls.some((c) => c.path.includes("status=failed"))).toBe(true));
    expect(screen.queryByRole("button", { name: "Next page" })).toBeNull();
  });
});

describe("Settings", () => {
  it("stores the operator key and shows role", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/settings", <Settings />, <Route path="/x" element={<div />} />);
    expect(await screen.findByTestId("settings-role")).toHaveTextContent("Viewer");
    await userEvent.type(screen.getByLabelText("Operator key"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(localStorage.getItem("kb.apiKey")).toBe("abc");
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(localStorage.getItem("kb.apiKey")).toBeNull();
    expect(screen.getByText(/"max_turns": 40/)).toBeInTheDocument();
  });
});
