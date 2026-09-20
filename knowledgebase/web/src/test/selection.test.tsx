import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resetChatBus } from "../chatBus";
import PageView from "../pages/PageView";
import { defaultResponder, mockFetch, renderAt } from "./harness";

const stubReducedMotion = () =>
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} }));

const QUIZ = { answer: "", sources: [], quiz: [{ q: "Which page is linked?", options: ["governance", "billing"], answer: 0, why: "It links there." }] };
const TOOLBAR = "Ask the librarian about the selected text";

/** jsdom has no layout: fake a selection of `text` whose range lives under `node`, 200px down the viewport. */
function stubSelection(text: string, node: Node) {
  const selection = {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => text,
    getRangeAt: () => ({ commonAncestorContainer: node, getBoundingClientRect: () => ({ top: 200, bottom: 220, left: 100, width: 300 }) }),
    removeAllRanges: () => {
      selection.isCollapsed = true;
    },
  };
  vi.stubGlobal("getSelection", () => selection);
  return selection;
}

const renderPage = (search = "") => renderAt({ pathname: "/kb/page/onboarding/README.md", search }, <PageView />, undefined, "/kb/page/*");
const settle = () => new Promise((resolve) => setTimeout(resolve, 250)); // past the toolbar's selectionchange settle delay

afterEach(() => {
  vi.unstubAllGlobals();
  resetChatBus();
});

describe("SelectionToolbar", () => {
  it("appears over a selection inside the article and sends Explain with the passage as context", async () => {
    stubReducedMotion();
    const calls = mockFetch(defaultResponder({ "/chat": { answer: "It means the page is healthy.", sources: [] } }));
    renderPage();
    const heading = await screen.findByRole("heading", { name: "Onboarding", level: 1 });
    expect(screen.queryByRole("toolbar")).toBeNull();
    stubSelection("Hello governance and code.", heading);
    fireEvent.mouseUp(heading);
    const toolbar = await screen.findByRole("toolbar", { name: TOOLBAR });
    expect(toolbar).toHaveStyle({ top: "152px" }); // above the selection: 200 - 40 - 8
    expect(screen.getByRole("button", { name: "Elaborate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Quiz me" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Explain" }));
    expect(screen.queryByRole("toolbar")).toBeNull();
    expect(screen.getByRole("dialog", { name: "Ask the librarian" })).toBeInTheDocument();
    expect(screen.getByText("About: Onboarding")).toBeInTheDocument();
    expect(screen.getByText("Explain this in plain language.")).toBeInTheDocument();
    expect(await screen.findByText("It means the page is healthy.")).toBeInTheDocument();
    const post = calls.find((c) => c.path === "/chat");
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      message: "Explain this in plain language.",
      history: [],
      mode: "explain",
      context: { path: "onboarding/README.md", title: "Onboarding", selection: "Hello governance and code." },
    });
    await userEvent.click(screen.getByRole("button", { name: "Clear context" }));
    expect(screen.queryByText("About: Onboarding")).toBeNull();
  });

  it("stays hidden for short, outside or oversized selections, shows once a selection settles, and closes on Escape", async () => {
    mockFetch(defaultResponder());
    renderPage();
    const heading = await screen.findByRole("heading", { name: "Onboarding", level: 1 });
    for (const [text, node] of [["too short", heading], ["Long enough, but selected outside the article.", document.body], ["x".repeat(2001), heading]] as const) {
      stubSelection(text, node);
      fireEvent(document, new Event("selectionchange"));
      fireEvent.mouseUp(node);
      await settle();
      expect(screen.queryByRole("toolbar")).toBeNull();
    }
    const outside = stubSelection("Someone's selection outside the article.", document.body);
    fireEvent.keyUp(document, { key: "Escape" });
    expect(outside.isCollapsed).toBe(false); // Escape only clears a selection the toolbar is up for
    const inside = stubSelection("Long enough and inside the article.", heading);
    fireEvent(document, new Event("selectionchange")); // a drag: shown once it settles, not per move
    expect(screen.queryByRole("toolbar")).toBeNull();
    expect(await screen.findByRole("toolbar", { name: TOOLBAR })).toBeInTheDocument();
    fireEvent.keyUp(document, { key: "Escape" });
    expect(screen.queryByRole("toolbar")).toBeNull();
    expect(inside.isCollapsed).toBe(true);
    fireEvent.mouseUp(heading); // the selection was collapsed by Escape, so nothing comes back
    expect(screen.queryByRole("toolbar")).toBeNull();
  });

  it("opens a whole-page quiz once when the page is opened with ?quiz=1", async () => {
    stubReducedMotion();
    const calls = mockFetch(defaultResponder({ "/chat": QUIZ }));
    renderPage("?quiz=1");
    expect(await screen.findByRole("dialog", { name: "Ask the librarian" })).toBeInTheDocument();
    expect(screen.getByText("Quiz me on this.")).toBeInTheDocument();
    expect(await screen.findByText("1. Which page is linked?")).toBeInTheDocument();
    expect(screen.getByText("About: Onboarding")).toBeInTheDocument();
    const posts = calls.filter((c) => c.path === "/chat");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0].init?.body))).toEqual({
      message: "Quiz me on this.",
      history: [],
      mode: "quiz",
      context: { path: "onboarding/README.md", title: "Onboarding" },
    });
  });
});
