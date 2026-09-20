import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { Profile } from "../api/types";
import { dismissNudge, readNudgeState, setNudgesEnabled, storageKey } from "../nudgeStore";
import Home from "../pages/Home";
import Settings from "../pages/Settings";
import { defaultResponder, errorResponse, mockFetch, profile, renderAt, signedIn, viewer, type Responder } from "./harness";

const DAY = 24 * 60 * 60 * 1000;
const ago = (days: number) => new Date(Date.now() - days * DAY).toISOString();
/** A page left five days ago, a page read twice, and a section never opened: three candidates for two slots. */
const busy: Profile = {
  ...profile,
  viewed: {
    "onboarding/README.md": { first_at: ago(6), last_at: ago(5), count: 1, title: "Onboarding" },
    "onboarding/day-one.md": { first_at: ago(2), last_at: ago(1), count: 2, title: "Day one" },
  },
  progress: [{ section: "onboarding", title: "Onboarding", viewed: 2, total: 2 }, { section: "governance", title: "Governance", viewed: 0, total: 1 }],
};
const responder = (p: unknown = busy) => defaultResponder({ "/me": signedIn, "/profile": p });
const LABEL = "Suggestions for you";
const region = () => screen.queryByRole("region", { name: LABEL });

describe("Nudges strip", () => {
  beforeEach(() => localStorage.clear());

  it("renders nothing for an anonymous reader and fetches no profile", async () => {
    const calls = mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/", <Home />);
    await screen.findByText("Start here");
    await waitFor(() => expect(calls.some((c) => c.path === "/me")).toBe(true)); // identity answered…
    await act(async () => {}); // …and every effect that could follow it has run
    expect(region()).toBeNull();
    expect(calls.some((c) => c.path === "/profile")).toBe(false);
  });

  it("shows up to two suggestions, each with a link to act on it", async () => {
    mockFetch(responder());
    renderAt("/", <Home />);
    const strip = await screen.findByRole("region", { name: LABEL });
    expect(strip).toHaveTextContent("Pick up where you left off");
    expect(strip).toHaveTextContent("You opened “Onboarding” a while ago");
    expect(strip).toHaveTextContent("Test yourself on Day one");
    expect(strip).not.toHaveTextContent("Governance");
    expect(screen.getByTestId("nudge-resume")).toHaveAttribute("href", "/kb/page/onboarding/README.md");
    expect(screen.getByTestId("nudge-quiz")).toHaveAttribute("href", "/kb/page/onboarding/day-one.md?quiz=1");
    expect(screen.getAllByRole("link", { name: /^Open: / })).toHaveLength(2);
  });

  it("dismissing hides a suggestion, promotes the next one, keeps focus in the strip and persists across a re-render", async () => {
    mockFetch(responder());
    const first = renderAt("/", <Home />);
    await screen.findByText("Pick up where you left off");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss: Pick up where you left off" }));
    expect(screen.queryByText("Pick up where you left off")).toBeNull();
    expect(await screen.findByText("You haven't opened Governance yet")).toBeInTheDocument();
    expect(screen.getByTestId("nudge-section")).toHaveAttribute("href", "/kb/governance");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("nudge-quiz")));
    expect(Object.keys(readNudgeState("u-1").dismissed)).toEqual(["resume:onboarding/README.md"]);
    expect(localStorage.getItem(storageKey("u-1"))).toContain("resume:onboarding/README.md");
    first.unmount();
    mockFetch(responder());
    renderAt("/", <Home />);
    await screen.findByText("You haven't opened Governance yet");
    expect(screen.queryByText("Pick up where you left off")).toBeNull();
  });

  it("moves focus to the page body when the last suggestion is dismissed", async () => {
    mockFetch(responder({ ...profile, viewed: {}, progress: [] }));
    renderAt("/", <Home />);
    const strip = await screen.findByRole("region", { name: LABEL });
    expect(strip).toHaveTextContent("Start with Onboarding");
    expect(screen.getByTestId("nudge-welcome")).toHaveAttribute("href", "/kb/onboarding");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss: Start with Onboarding" }));
    expect(region()).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(document.getElementById("main")));
  });

  it("never suggests the page the reader is already on", async () => {
    dismissNudge("u-1", "resume:onboarding/README.md");
    mockFetch(responder());
    renderAt("/kb/governance", <Home />);
    const strip = await screen.findByRole("region", { name: LABEL });
    expect(strip).toHaveTextContent("Test yourself on Day one");
    expect(strip).not.toHaveTextContent("Governance");
  });

  it("stays hidden — and fetches nothing — when the reader turned suggestions off", async () => {
    setNudgesEnabled("u-1", false);
    const calls = mockFetch(responder());
    renderAt("/settings", <Settings />);
    await screen.findByTestId("settings-user");
    expect(region()).toBeNull();
    // Settings itself loads the profile (persona card); the strip is the only thing here that would ask for sections.
    expect(calls.some((c) => c.path.startsWith("/sections"))).toBe(false);
  });

  it("renders nothing when there is nothing to suggest, or when the profile cannot be loaded", async () => {
    const quizzed: Profile = { ...busy, viewed: { "onboarding/README.md": { ...busy.viewed["onboarding/README.md"], count: 5, last_at: ago(0) } }, quizzes: [{ path: "onboarding/README.md", at: ago(0), score: 1, total: 1 }], progress: [] };
    mockFetch(responder(quizzed));
    const first = renderAt("/", <Home />);
    await screen.findByTestId("continue-reading");
    expect(region()).toBeNull();
    first.unmount();
    const calls = mockFetch(responder(errorResponse(401, "no session")));
    renderAt("/", <Home />);
    await screen.findByText("Start here");
    await waitFor(() => expect(calls.filter((c) => c.path === "/profile").length).toBeGreaterThan(0)); // the fetch happened…
    await act(async () => {}); // …and failed; only then does "nothing rendered" mean anything
    expect(region()).toBeNull();
  });
});

describe("Suggestions setting", () => {
  beforeEach(() => localStorage.clear());

  it("turns the strip off and on for this reader", async () => {
    mockFetch(responder());
    renderAt("/settings", <Settings />);
    const toggle = await screen.findByRole("switch", { name: "Suggestions" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByRole("region", { name: LABEL })).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("nudges-state")).toHaveTextContent("Off");
    expect(region()).toBeNull();
    expect(readNudgeState("u-1").enabled).toBe(false);
    await userEvent.click(toggle);
    expect(screen.getByTestId("nudges-state")).toHaveTextContent("On");
    expect(await screen.findByRole("region", { name: LABEL })).toBeInTheDocument();
  });

  it("is not offered to an anonymous reader", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/settings", <Settings />);
    await screen.findByText("Single sign-on is not configured on this server.");
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("'Delete my data' also forgets what this browser kept for the reader", async () => {
    dismissNudge("u-1", "resume:onboarding/README.md");
    setNudgesEnabled("u-1", false);
    const base = responder();
    const withDelete: Responder = (path, init) => (path === "/profile" && init?.method === "DELETE" ? new Response(null, { status: 204 }) : base(path, init));
    mockFetch(withDelete);
    renderAt("/settings", <Settings />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete everything" }));
    expect(await screen.findByText("Deleted.")).toBeInTheDocument();
    await waitFor(() => expect(localStorage.getItem(storageKey("u-1"))).toBeNull());
    expect(readNudgeState("u-1")).toEqual({ enabled: true, dismissed: {} });
    expect(screen.getByRole("switch", { name: "Suggestions" })).toHaveAttribute("aria-checked", "true");
  });
});
