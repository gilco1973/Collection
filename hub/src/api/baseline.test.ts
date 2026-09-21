import { describe, expect, it } from "vitest";
import { BASELINE, baselineFor, missingBaseline, withBaseline } from "./baseline";
import { DRAFT_BRIEF } from "./mock/fixtures";
import type { BriefContent } from "./schemas";

const noTools: BriefContent = { ...DRAFT_BRIEF.content, dataAndTools: { systems: [], tools: [], dataClasses: ["internal"], tierCeiling: "R" } };
const withTools: BriefContent = {
  ...DRAFT_BRIEF.content,
  dataAndTools: { ...DRAFT_BRIEF.content.dataAndTools, reuses: [{ id: "employee-assistant", name: "Employee assistant", kind: "service" }] },
};

describe("the harness baseline", () => {
  it("is nothing without a tool and the whole harness set with any tool", () => {
    expect(baselineFor(noTools)).toEqual([]);
    expect(baselineFor(withTools).map((b) => b.id)).toEqual([
      "governed-action-loop",
      "untrusted-input-guard",
      "cited-llm-engine",
      "audit-chain",
      "ids-only-logging",
    ]);
    expect(BASELINE.every((b) => b.required && b.kind === "component" && b.why.length > 20)).toBe(true);
  });

  it("merges into the brief's reuses as required entries and keeps the person's own choices", () => {
    expect(withBaseline(noTools)).toBe(noTools);
    const merged = withBaseline(withTools);
    const reuses = (merged.dataAndTools as { reuses: Array<{ id: string; required?: boolean }> }).reuses;
    expect(reuses.filter((r) => r.required).map((r) => r.id)).toEqual(BASELINE.map((b) => b.id));
    expect(reuses.find((r) => r.id === "employee-assistant")?.required).toBeUndefined();
    expect(missingBaseline(merged)).toEqual([]);
    expect(missingBaseline(withTools).length).toBe(5);
    // Idempotent: filing twice does not duplicate.
    expect((withBaseline(merged).dataAndTools as { reuses: unknown[] }).reuses).toHaveLength(6);
  });
});
