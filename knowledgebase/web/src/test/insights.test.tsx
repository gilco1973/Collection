import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Insights } from "../api/insightsTypes";
import Audits from "../pages/Audits";
import { defaultResponder, errorResponse, mockFetch, renderAt, viewer } from "./harness";

const insights: Insights = {
  generated_at: "2026-09-18T12:00:00Z", k: 5, window_days: 30, suppressed: 1,
  pages: {
    "onboarding/README.md": { views: 7, readers: 6, problems: { outdated: 2, unclear: 1 }, quiz_attempts: 3, quiz_fail_rate: 0.3333, chat_citations: 2 },
    "governance/README.md": { views: null, readers: null, problems: { incorrect: 1 }, quiz_attempts: null, quiz_fail_rate: null, chat_citations: 0 },
  },
  unanswered: { mode: { ask: 1, quiz: 1 }, lang: { en: 1, es: 1 } },
};
const EMPTY = "No insights yet — refresh to compute them";

afterEach(() => vi.unstubAllGlobals());

describe("Insights tab", () => {
  it("is not offered to viewers", async () => {
    const calls = mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/audits", <Audits />);
    expect(await screen.findByRole("link", { name: "audit-1" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Insights" })).toBeNull();
    expect(calls.some((c) => c.path === "/insights")).toBe(false);
  });

  it("renders the three tables for an operator", async () => {
    mockFetch(defaultResponder({ "/insights": insights }));
    renderAt("/audits", <Audits />);
    await userEvent.click(await screen.findByRole("tab", { name: "Insights" }));
    expect(await screen.findByRole("heading", { name: "Pages by problem reports" })).toBeInTheDocument();
    expect(screen.getAllByText("onboarding/README.md")).toHaveLength(2); // by problems and by fail rate
    expect(screen.getAllByText("governance/README.md")).toHaveLength(1); // no fail rate below k
    expect(screen.getByText("outdated 2, unclear 1")).toBeInTheDocument();
    expect(screen.getAllByText("hidden").length).toBeGreaterThanOrEqual(2); // readers and views of the suppressed page
    expect(screen.getByText("33%")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Unanswered questions" })).toBeInTheDocument();
    expect(screen.getByText("quiz")).toBeInTheDocument();
    expect(screen.getByText("es")).toBeInTheDocument();
    expect(screen.getByText(/fewer than 5 readers/)).toBeInTheDocument();
    expect(screen.getByText(/hidden pages: 1/)).toBeInTheDocument();
    expect(screen.queryByText("audit-1")).toBeNull(); // the list is the other tab
    await userEvent.click(screen.getByRole("tab", { name: "Audit runs" }));
    expect(await screen.findByRole("link", { name: "audit-1" })).toBeInTheDocument();
  });

  it("shows the empty state before generation and refreshes with a POST", async () => {
    let generated = false;
    const calls = mockFetch((path, init) => {
      if (path === "/insights/refresh") { generated = true; return insights; }
      if (path === "/insights") return generated ? insights : errorResponse(404, "no insights yet");
      return defaultResponder()(path, init);
    });
    renderAt({ pathname: "/audits", search: "?tab=insights" }, <Audits />);
    expect(await screen.findByText(EMPTY)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/insights/refresh" && c.init?.method === "POST")).toBe(true));
    expect(await screen.findByRole("heading", { name: "Pages by problem reports" })).toBeInTheDocument();
    expect(screen.queryByText(EMPTY)).toBeNull();
  });

  it("shows an API error and lets the operator retry", async () => {
    mockFetch(defaultResponder({ "/insights": errorResponse(500, "disk on fire") }));
    renderAt({ pathname: "/audits", search: "?tab=insights" }, <Audits />);
    expect(await screen.findByText("disk on fire")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
