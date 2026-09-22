import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Brief } from "../../api/types";
import { DRAFT_BRIEF } from "../../api/mock/fixtures";
import { briefsWaitingFor, WaitingToFile } from "./WaitingToFile";

const brief = (over: Partial<Brief>): Brief => ({ ...structuredClone(DRAFT_BRIEF), ...over });

describe("the team lead's briefs waiting to be filed", () => {
  it("lists other people's open drafts, newest first, never the lead's own or a filed one", () => {
    const briefs = [
      brief({ id: "mine", createdBy: "u_gk", updatedAt: "2026-09-20T00:00:00Z" }),
      brief({ id: "old", createdBy: "u_ap", updatedAt: "2026-09-01T00:00:00Z" }),
      brief({ id: "filed", createdBy: "u_ap", status: "filed", updatedAt: "2026-09-21T00:00:00Z" }),
      brief({ id: "new", createdBy: "u_so", status: "needs_info", updatedAt: "2026-09-19T00:00:00Z" }),
    ];
    expect(briefsWaitingFor(briefs, "u_gk").map((b) => b.id)).toEqual(["new", "old"]);
    expect(briefsWaitingFor(undefined, "u_gk")).toEqual([]);
  });

  it("renders nothing when there is nothing waiting, so the artboards' screens are unchanged", () => {
    const { container } = render(
      <MemoryRouter>
        <WaitingToFile briefs={[]} teams={[]} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("names each brief, its team and ceiling, with a link to open it", () => {
    render(
      <MemoryRouter>
        <WaitingToFile briefs={[brief({ id: "brf_x", createdBy: "u_ap" })]} teams={[{ id: "team-payments-ops", name: "Payments operations" }]} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Waiting for you to file" })).toBeInTheDocument();
    expect(screen.getByText("Payments returns triage for the collections desk")).toBeInTheDocument();
    expect(screen.getByText(/Payments operations/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open/ })).toHaveAttribute("href", "/build/intake/brf_x");
  });
});
