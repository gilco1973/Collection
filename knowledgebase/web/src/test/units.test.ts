import { describe, expect, it } from "vitest";
import { applyDirection, changeLanguage, readStoredLanguage } from "../i18n";
import { resolveInternal, stripLeadingHeading } from "../components/markdownLinks";
import { ApiError, readApiKey, storeApiKey } from "../api/client";

describe("i18n", () => {
  it("applies RTL for Hebrew and persists the choice", async () => {
    await changeLanguage("he");
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(readStoredLanguage()).toBe("he");
    await changeLanguage("en");
    expect(document.documentElement.getAttribute("dir")).toBe("ltr");
    applyDirection("es");
    expect(document.documentElement.getAttribute("lang")).toBe("es");
  });
});

describe("markdown link resolution", () => {
  it("resolves relative paths and directories", () => {
    expect(resolveInternal("onboarding/README.md", "day-one.md")).toBe("/kb/page/onboarding/day-one.md");
    expect(resolveInternal("onboarding/README.md", "../governance/README.md#x")).toBe("/kb/page/governance/README.md");
    expect(resolveInternal("wiki/decision-records/README.md", "../../governance/")).toBe("/kb/page/governance/README.md");
  });
});

describe("leading heading", () => {
  it("strips only a duplicate title heading", () => {
    expect(stripLeadingHeading("# Onboarding\n\nbody", "Onboarding")).toBe("\nbody");
    expect(stripLeadingHeading("# Other\n\nbody", "Onboarding")).toBe("# Other\n\nbody");
    expect(stripLeadingHeading("body only", "Onboarding")).toBe("body only");
  });
});

describe("api key storage and errors", () => {
  it("round-trips and clears", () => {
    storeApiKey("k");
    expect(readApiKey()).toBe("k");
    storeApiKey("");
    expect(readApiKey()).toBe("");
    const err = new ApiError(409, "conflict", "r1");
    expect(err.status).toBe(409);
    expect(err.requestId).toBe("r1");
  });
});
