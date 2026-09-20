import { describe, expect, it } from "vitest";
import { briefContentSchema, issuesToFieldErrors, validateStep, BRIEF_STEPS } from "./schemas";
import { DRAFT_BRIEF } from "./mock/fixtures";

describe("intake brief schema", () => {
  it("lists the six steps in §7.11 order", () => {
    expect(BRIEF_STEPS).toEqual(["useCase", "people", "dataAndTools", "model", "outcome", "review"]);
  });

  it("accepts the completed steps of the artboard draft", () => {
    expect(validateStep("useCase", DRAFT_BRIEF.content.useCase)).toEqual({});
    expect(validateStep("people", DRAFT_BRIEF.content.people)).toEqual({});
  });

  it("requires the tier ceiling to cover every tool", () => {
    const errs = validateStep("dataAndTools", DRAFT_BRIEF.content.dataAndTools);
    expect(Object.keys(errs)).toEqual(["dataAndTools.tierCeiling"]);
    expect(errs["dataAndTools.tierCeiling"][0]).toMatch(/cos_reverse_fee \(W1\)/);
    expect(validateStep("dataAndTools", { ...DRAFT_BRIEF.content.dataAndTools, tierCeiling: "W1" })).toEqual({});
  });

  it("refuses restricted data for a first consumer", () => {
    const errs = validateStep("dataAndTools", { ...DRAFT_BRIEF.content.dataAndTools, tierCeiling: "W1", dataClasses: ["internal", "restricted"] });
    expect(errs["dataAndTools.dataClasses"][0]).toMatch(/Restricted data/);
  });

  it("caps the tool list at the 15-tool session ceiling", () => {
    const tools = Array.from({ length: 16 }, (_, i) => ({ name: `t${i}`, tier: "R" as const, classes: ["internal" as const] }));
    const errs = validateStep("dataAndTools", { ...DRAFT_BRIEF.content.dataAndTools, tools });
    expect(errs["dataAndTools.tools"][0]).toMatch(/15-tool/);
  });

  it("asks for one outcome metric with a baseline that differs from the target", () => {
    expect(validateStep("outcome", { metric: "", unit: "", baseline: 1, target: 1, measuredOn: "" })).toMatchObject({
      "outcome.metric": [expect.stringMatching(/PLT-ONB-10/)],
      "outcome.unit": [expect.any(String)],
      "outcome.measuredOn": [expect.any(String)],
      "outcome.target": [expect.stringMatching(/differ/)],
    });
  });

  it("requires the acknowledgement to file", () => {
    const r = briefContentSchema.safeParse(DRAFT_BRIEF.content);
    expect(r.success).toBe(false);
    const errs = r.success ? {} : issuesToFieldErrors(r.error.issues);
    expect(errs["review.acknowledged"]).toBeDefined();
  });

  it("keys field errors by dotted path with the step prefix", () => {
    expect(issuesToFieldErrors([{ code: "custom", path: ["name"], message: "m" }] as never, "useCase")).toEqual({ "useCase.name": ["m"] });
  });
});
