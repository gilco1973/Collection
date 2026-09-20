import { describe, expect, it } from "vitest";
import { PRINCIPALS } from "../../api/mock/fixtures";
import { EMPTY_FACTS, journey, nudge, pageNote, suggestedPersona, TOURS, type Facts } from "./model";

const facts = (over: Partial<Facts>): Facts => ({ ...EMPTY_FACTS, ...over });

describe("the guide's model", () => {
  it("suggests a persona from the principal and lets the person overrule it", () => {
    expect(suggestedPersona(PRINCIPALS.platform)).toBe("decide");
    expect(suggestedPersona(PRINCIPALS.employee)).toBe("use");
    expect(suggestedPersona(PRINCIPALS.investigator)).toBe("build");
    expect(suggestedPersona(PRINCIPALS.security)).toBe("build");
    expect(suggestedPersona(undefined)).toBe("build");
  });

  it("walks a builder along a path whose steps are ticked by the hub's own facts", () => {
    const fresh = journey(facts({ persona: "build" }));
    expect(fresh.map((s) => s.state)).toEqual(["on", "todo", "todo", "todo", "todo", "todo", "todo", "todo"]);
    const later = journey(
      facts({
        persona: "build",
        visited: ["/discover", "/discover/agents/incident-first-read-agent"],
        ticked: ["b.run"],
        briefs: { drafts: 1, filed: 0 },
      }),
    );
    expect(later.slice(0, 4).every((s) => s.state === "done")).toBe(true);
    expect(later[4]).toMatchObject({ id: "b.file", state: "on" });
    expect(later.find((s) => s.id === "b.run")?.command).toContain("python3 example.py");
  });

  it("gives a leader a shorter path that includes a question, not only pages", () => {
    const steps = journey(facts({ persona: "decide", visited: ["/learn"] }));
    expect(steps[0].state).toBe("done");
    expect(steps[1]).toMatchObject({ id: "d.cannot", state: "on" });
    expect(steps.find((s) => s.id === "d.controls")?.ask).toMatch(/stops an agent/);
    expect(steps.filter((s) => s.manual).length).toBe(2);
  });

  it("suggests the one next step for the page and the facts, and never a dismissed one", () => {
    expect(nudge(facts({ persona: "build", page: "/discover" }))?.id).toBe("build.agent");
    expect(nudge(facts({ persona: "build", page: "/discover", visited: ["/discover/agents/incident-first-read-agent"] }))?.id).toBe("tour.build");
    expect(nudge(facts({ persona: "build", page: "/discover", dismissed: ["build.agent"], toursDone: ["build"] }))).toBeUndefined();
    // Work waiting on the person outranks orientation.
    const waiting = nudge(facts({ persona: "build", page: "/discover", shelf: { total: 29, onShelf: 0, waitingForMe: 3 } }));
    expect(waiting?.text).toContain("3 components are waiting");
    expect(waiting?.cta?.route).toBe("/build/shelf/sign-offs");
    expect(nudge(facts({ persona: "build", page: "/build/shelf/sign-offs", shelf: { total: 29, onShelf: 0, waitingForMe: 3 } }))?.id).not.toMatch(/^sign/);
    const briefs = { drafts: 1, filed: 0, draftName: "Returns triage", draftId: "b1", draftStep: "the model" };
    const draft = nudge(facts({ persona: "build", page: "/learn", briefs }));
    expect(draft?.text).toContain("“Returns triage” is waiting at the model");
    expect(draft?.cta?.route).toBe("/build/intake/b1");
    // A leader hears about the page first; their own open work comes once that is dismissed.
    expect(nudge(facts({ persona: "decide", page: "/learn", briefs }))?.id).toBe("decide.open");
    expect(nudge(facts({ persona: "decide", page: "/learn", briefs, dismissed: ["decide.open", "tour.decide"] }))?.cta?.route).toBe("/build/intake/b1");
  });

  it("talks to a leader about what cannot happen, on the pages where it matters", () => {
    const onListing = nudge(facts({ persona: "decide", page: "/discover/agents/incident-first-read-agent" }));
    expect(onListing?.text).toMatch(/entire permission list/);
    expect(onListing?.cta?.ask).toMatch(/stops an agent/);
    expect(nudge(facts({ persona: "decide", page: "/assistant/employee-assistant" }))?.text).toMatch(/has no tools/);
    expect(nudge(facts({ persona: "decide", page: "/build/shelf/sign-offs" }))?.text).toMatch(/four attestations/);
  });

  it("describes every page for every persona and points tours only at anchored targets", () => {
    for (const page of [
      "/discover",
      "/discover/agents/x",
      "/discover/tools/y",
      "/assistant/employee-assistant",
      "/workspace",
      "/build/intake",
      "/build/intake/b1",
      "/build/shelf/sign-offs",
      "/build/shelf/onboarding",
      "/learn",
      "/settings",
      "/nope",
    ]) {
      const n = pageNote(page);
      expect(n.title).toBeTruthy();
      expect(n.note.build && n.note.decide && n.note.use).toBeTruthy();
    }
    const anchors = new Set([
      "discover-tabs",
      "listing-catalog",
      "intake-form",
      "onboarding-tracker",
      "signoff-queue",
      "signoff-form",
      "learn-roads",
      "learn-collection",
      "workspace-usage",
      "workspace-requests",
      "assistant-composer",
    ]);
    for (const t of Object.values(TOURS)) for (const s of t.steps) expect(anchors.has(s.target), `${t.title}: ${s.target}`).toBe(true);
  });
});

describe("the rules mode reads markdown as prose", () => {
  it("flattens tables and marks", async () => {
    const { plain, ask } = await import("../../api/mock/guideRules");
    expect(plain("## The tiers\n| Tier | Who says yes |\n| --- | --- |\n| R | Nobody |\n- **bold** and `code` and [a link](docs/x.md)")).toBe(
      "The tiers\nTier · Who says yes.\nR · Nobody.\n• bold and code and a link",
    );
    const out = ask("Can the agent move money on its own?", "leadership");
    expect(out.answer).not.toContain("| ---");
    expect(out.answer).not.toContain("**");
  });
});
