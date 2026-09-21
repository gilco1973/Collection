import { describe, expect, it } from "vitest";
import { PRINCIPALS } from "../api/mock/fixtures";
import { isTeamLead, permits, primaryRole } from "./permits";

const gk = PRINCIPALS.gk;
const employee = PRINCIPALS.employee;
const investigator = PRINCIPALS.investigator;

describe("front-end permits", () => {
  it("grants nothing to nobody", () => {
    expect(permits(undefined, "hub.discover")).toBe(false);
  });

  it("opens a consumer by entitlement, not by role", () => {
    expect(permits(gk, "consumer.open", { consumerId: "investigation-triage" })).toBe(true);
    expect(permits(employee, "consumer.open", { consumerId: "investigation-triage" })).toBe(false);
    expect(permits(gk, "consumer.open")).toBe(false);
  });

  it("lets the owner sign by name and AI security by role, nobody else", () => {
    expect(permits(gk, "shelf.sign", { signoffRole: "owner", owner: "gil.klainert" })).toBe(true);
    expect(permits(gk, "shelf.sign", { signoffRole: "owner", owner: "someone.else" })).toBe(false);
    expect(permits(gk, "shelf.sign", { signoffRole: "ai_security", owner: "gil.klainert" })).toBe(false);
    expect(permits(PRINCIPALS.security, "shelf.sign", { signoffRole: "ai_security" })).toBe(true);
    expect(permits(PRINCIPALS.security, "shelf.sign", { signoffRole: "owner", owner: "gil.klainert" })).toBe(false);
    expect(permits(employee, "shelf.sign", { signoffRole: "ai_security" })).toBe(false);
    expect(permits(gk, "shelf.sign")).toBe(false);
  });

  it("lets anyone ask for access to what they lack, and only that", () => {
    expect(permits(employee, "consumer.request_access", { consumerId: "investigation-triage" })).toBe(true);
    expect(permits(employee, "consumer.request_access", { consumerId: "employee-assistant" })).toBe(false);
  });

  it("caps ladder requests at the person's own ceiling and needs the grant", () => {
    expect(permits(investigator, "consumer.request_ladder", { consumerId: "investigation-triage", ladder: "L1" })).toBe(true);
    expect(permits(investigator, "consumer.request_ladder", { consumerId: "investigation-triage", ladder: "L2" })).toBe(false);
    expect(permits(employee, "consumer.request_ladder", { consumerId: "investigation-triage", ladder: "L0" })).toBe(false);
    expect(permits(gk, "consumer.request_ladder", { consumerId: "investigation-triage", ladder: "L2" })).toBe(true);
  });

  it("lets an author file their own brief and a lead file anyone's", () => {
    expect(permits(employee, "brief.file", { ownedByMe: true })).toBe(true);
    expect(permits(employee, "brief.file", { ownedByMe: false })).toBe(false);
    expect(permits(employee, "brief.file")).toBe(false);
    expect(permits(gk, "brief.file")).toBe(true);
  });

  it("names the primary role and team leads", () => {
    expect(primaryRole(gk)).toBe("ops.lead");
    expect(primaryRole(employee)).toBe("employee");
    expect(isTeamLead(gk, "team-payments-ops")).toBe(true);
    expect(isTeamLead(investigator)).toBe(false);
  });
});

describe("a brief needs a team", () => {
  it("is not offered to a person in no team", async () => {
    const { permits } = await import("./permits");
    const base = { id: "u_x", name: "X", email: "x@bank.example", initials: "X", tenant: "t", roles: [], ladder: "L0", channel: "operator", teams: [], costCentre: "", entitlements: [], preferences: {} } as never;
    expect(permits(base, "brief.create")).toBe(false);
    expect(permits({ ...(base as object), teams: [{ id: "t1", name: "T", lead: false }] } as never, "brief.create")).toBe(true);
  });
});
