import { describe, expect, it } from "vitest";
import type { ShelfEntry } from "../../api/types";
import { counts, groupByStage, openRolesFor, signoffView } from "./stages";

const base: ShelfEntry = {
  name: "audit-chain",
  title: "Audit chain",
  version: "1.0.0",
  kind: "tool",
  language: "python",
  owner: "gil.klainert",
  status: "ready",
  summary: "",
  signoff: { owner: null, ai_security: null },
  signed: false,
  state: "owner pending; AI security pending",
  usedIn: [],
  stage: { index: 1, of: 6, label: "built", next: "use it once" },
  gates: { readme: true, walkthrough: true, example: true, tests: true, spec: true },
  test: "python3 -m unittest",
  exampleRun: "python3 example.py",
  hubPath: "/discover/tools/audit-chain",
  repoPath: "components/python/audit-chain",
  recorded: {},
  youMaySign: [],
};

describe("shelf stage helpers", () => {
  it("reads a sign-off as signed, recorded, stale or pending, in that order of authority", () => {
    expect(signoffView(base, "owner").kind).toBe("pending");
    const recorded = {
      ...base,
      recorded: {
        owner: {
          id: "so_1",
          component: "audit-chain",
          role: "owner" as const,
          by: "A",
          email: "a@x.example",
          date: "2026-09-20",
          version: "1.0.0",
          attest: { testsGreen: true, exampleRun: true, walkthroughRead: true, rulesRead: true },
          recordedAt: "",
        },
      },
    };
    expect(signoffView(recorded, "owner").kind).toBe("recorded");
    const stale = { ...base, signoff: { ...base.signoff, owner: { by: "A", date: "2026-01-01", version: "0.9.0" } } };
    expect(signoffView(stale, "owner")).toMatchObject({ kind: "stale", chip: "crit" });
    const signed = { ...base, signoff: { ...base.signoff, owner: { by: "A", date: "2026-01-01", version: "1.0.0" } } };
    expect(signoffView(signed, "owner")).toMatchObject({ kind: "signed", text: "A · 2026-01-01" });
  });

  it("offers the form only for roles the person may sign that are still open on a ready component", () => {
    expect(openRolesFor({ ...base, youMaySign: ["owner", "ai_security"] })).toEqual(["owner", "ai_security"]);
    expect(openRolesFor({ ...base, youMaySign: ["owner"], signoff: { ...base.signoff, owner: { by: "A", date: "2026-01-01", version: "1.0.0" } } })).toEqual(
      [],
    );
    expect(openRolesFor({ ...base, youMaySign: ["owner"], status: "draft" })).toEqual([]);
  });

  it("groups the tracker furthest along first and counts what waits on whom", () => {
    const both = { by: "A", date: "2026-01-01", version: "1.0.0" };
    const shelf = { ...base, name: "b", signed: true, signoff: { owner: both, ai_security: both }, stage: { ...base.stage, index: 5, label: "on the shelf" } };
    const groups = groupByStage([base, shelf]);
    expect(groups.map((g) => g.key)).toEqual(["shelf", "built"]);
    expect(counts([base, shelf])).toMatchObject({ total: 2, signed: 1, awaitingOwner: 1, awaitingSecurity: 1, recorded: 0 });
  });
});
