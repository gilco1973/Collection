import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route } from "react-router-dom";
import AuditDetail from "../pages/AuditDetail";
import Rollback from "../pages/Rollback";
import RunAudit from "../pages/RunAudit";
import { audit, defaultResponder, errorResponse, mockFetch, renderAt, viewer } from "./harness";

afterEach(() => vi.unstubAllGlobals());

describe("RunAudit", () => {
  it("starts a dry run for an operator", async () => {
    const calls = mockFetch(defaultResponder({ "/audits": { audit_id: "audit-9", dry_run: true, forced_dry_run: false } }));
    renderAt("/audits/new", <RunAudit />, <Route path="/audits/:id" element={<div>detail-page</div>} />, "/audits/new");
    await userEvent.click(await screen.findByLabelText("frontmatter"));
    await userEvent.click(screen.getByLabelText("structure"));
    await userEvent.type(screen.getByLabelText("Max turns"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Start dry run" }));
    expect(await screen.findByText("detail-page")).toBeInTheDocument();
    const post = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ type: "agent", dry_run: true, capabilities: ["links"], max_turns: 5 });
  });

  it("requires a typed LIVE token and a reason for live runs", async () => {
    const calls = mockFetch(defaultResponder({ "/audits": { audit_id: "audit-9", dry_run: false, forced_dry_run: false } }));
    renderAt("/audits/new", <RunAudit />, <Route path="/audits/:id" element={<div>detail-page</div>} />, "/audits/new");
    await userEvent.click(await screen.findByRole("radio", { name: /LIVE/ }));
    await userEvent.click(screen.getByRole("button", { name: "Start LIVE audit" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toBeInTheDocument();
    const confirm = screen.getAllByRole("button", { name: "Start LIVE audit" })[1];
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Reason"), "quarterly frontmatter clean-up");
    await userEvent.type(screen.getByLabelText("Type LIVE to confirm"), "LIVE");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
    const post = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ dry_run: false, reason: "quarterly frontmatter clean-up" });
  });

  it("blocks viewers and shows API errors", async () => {
    mockFetch(defaultResponder({ "/me": viewer, "/audits": errorResponse(403, "operator role required") }));
    renderAt("/audits/new", <RunAudit />);
    expect(await screen.findByText(/Only operators can start audits/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start dry run" })).toBeNull(); // no form at all for a viewer
    expect(screen.queryByRole("radio")).toBeNull();
  });
});

describe("AuditDetail", () => {
  it("renders header, tabs, and cancel for a running audit", async () => {
    const calls = mockFetch(defaultResponder({ "/audits/audit-1/cancel": { status: "cancelling" }, "/audits/audit-1": audit({ status: "in_progress" }) }));
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    expect(await screen.findByRole("heading", { name: "audit-1" })).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("broken link")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Actions" }));
    expect(screen.getByText("Proposed (dry run)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Roll back" })).toHaveAttribute("href", "/audits/audit-1/actions/act-1/rollback");
    await userEvent.click(screen.getByRole("tab", { name: "Review queue" }));
    expect(screen.getByText("owner must review")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Tool trail" }));
    expect(screen.getAllByText("Denied").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Failed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Summary" }));
    expect(screen.getByRole("heading", { name: "Done" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel audit" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/audits/audit-1/cancel")).toBe(true));
    expect(await screen.findByText("Cancelling…")).toBeInTheDocument();
  });

  it("shows empty tabs, errors and the forced-dry notice", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1": audit({ findings: [], fixes_applied: [], manual_review_needed: [], tool_calls: [], ai_summary: null, error: "boom", dry_run: true }) }));
    renderAt({ pathname: "/audits/audit-1", state: { forced: true } }, <AuditDetail />, undefined, "/audits/:id");
    expect(await screen.findByText("No findings.")).toBeInTheDocument();
    expect(screen.getByText("Live was requested but the server forced a dry run.")).toBeInTheDocument();
    expect(screen.getByText(/Error: boom/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Actions" }));
    expect(screen.getByText("No actions.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Review queue" }));
    expect(screen.getByText("Nothing waiting for a human.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Tool trail" }));
    expect(screen.getByText("No tool calls recorded.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Summary" }));
    expect(screen.getByText("The librarian left no summary.")).toBeInTheDocument();
  });

  it("reports a missing audit", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1": errorResponse(404, "no report") }));
    renderAt("/audits/audit-1", <AuditDetail />, undefined, "/audits/:id");
    expect(await screen.findByText("no report")).toBeInTheDocument();
  });
});

describe("Rollback", () => {
  it("requires token and reason, supports force, and navigates back", async () => {
    const calls = mockFetch(defaultResponder({ "/audits/audit-1/actions/act-1/rollback": { action: audit().fixes_applied[0] } }));
    renderAt("/audits/audit-1/actions/act-1/rollback", <Rollback />, <Route path="/audits/:id" element={<div>detail-page</div>} />, "/audits/:id/actions/:actionId/rollback");
    const confirm = await screen.findByRole("button", { name: "Roll back" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Reason"), "undo the status change");
    await userEvent.type(screen.getByLabelText("Type ROLLBACK to confirm"), "ROLLBACK");
    await userEvent.click(screen.getByLabelText(/Force/));
    await userEvent.click(confirm);
    expect(await screen.findByText("detail-page")).toBeInTheDocument();
    const post = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ reason: "undo the status change", force: true });
  });

  it("shows conflicts and unknown actions", async () => {
    mockFetch(defaultResponder({ "/audits/audit-1/actions/act-1/rollback": errorResponse(409, "page changed") }));
    renderAt("/audits/audit-1/actions/act-1/rollback", <Rollback />, undefined, "/audits/:id/actions/:actionId/rollback");
    await userEvent.type(await screen.findByLabelText("Reason"), "undo the status change");
    await userEvent.type(screen.getByLabelText("Type ROLLBACK to confirm"), "ROLLBACK");
    await userEvent.click(screen.getByRole("button", { name: "Roll back" }));
    expect(await screen.findByText("page changed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    mockFetch(defaultResponder());
    renderAt("/audits/audit-1/actions/nope/rollback", <Rollback />, undefined, "/audits/:id/actions/:actionId/rollback");
    expect(await screen.findByText("No action 'nope' in this audit.")).toBeInTheDocument();
    mockFetch(defaultResponder());
    renderAt("/audits/audit-1/actions/act-2/rollback", <Rollback />, undefined, "/audits/:id/actions/:actionId/rollback");
    expect(await screen.findByText(/only proposed in a dry run/)).toBeInTheDocument();
  });
});
