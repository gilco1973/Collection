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
