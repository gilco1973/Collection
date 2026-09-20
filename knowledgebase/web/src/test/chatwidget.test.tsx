import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { openChat, resetChatBus } from "../chatBus";
import Home from "../pages/Home";
import { defaultResponder, errorResponse, mockFetch, renderAt } from "./harness";

const stubReducedMotion = () =>
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: true, // skip the typewriter timer in these tests; TypewriterText has its own coverage
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));

afterEach(() => {
  vi.unstubAllGlobals();
  resetChatBus();
});

describe("ChatWidget", () => {
  it("starts closed and opens on click", async () => {
    stubReducedMotion();
    mockFetch(defaultResponder());
    renderAt("/", <Home />);
    expect(screen.queryByRole("dialog", { name: "Ask the librarian" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Ask the librarian" }));
    expect(screen.getByRole("dialog", { name: "Ask the librarian" })).toBeInTheDocument();
    expect(screen.getByText("Ask anything about this knowledge base, by typing or by voice.")).toBeInTheDocument();
  });

  it("sends a question and shows the librarian's answer with its sources as links", async () => {
    stubReducedMotion();
    const calls = mockFetch(
      defaultResponder({
        "/chat": { answer: "Start with the AI policy.", sources: [{ path: "onboarding/README.md", title: "Onboarding" }] },
      }),
    );
    renderAt("/", <Home />);
    await userEvent.click(screen.getByRole("button", { name: "Ask the librarian" }));
    await userEvent.type(screen.getByPlaceholderText("Ask a question…"), "how do I get started?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByText("how do I get started?")).toBeInTheDocument();
    expect(await screen.findByText("Start with the AI policy.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Onboarding" })).toHaveAttribute("href", "/kb/page/onboarding/README.md");
    const post = calls.find((c) => c.path === "/chat");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ message: "how do I get started?", history: [] });
  });

  it("shows an error message when the request fails", async () => {
    stubReducedMotion();
    mockFetch(defaultResponder({ "/chat": errorResponse(502, "boom") }));
    renderAt("/", <Home />);
    await userEvent.click(screen.getByRole("button", { name: "Ask the librarian" }));
    await userEvent.type(screen.getByPlaceholderText("Ask a question…"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("holds a toolbar action until the turn in flight has finished, then sends it", async () => {
    stubReducedMotion();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const base = defaultResponder();
    const chats: string[] = [];
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/^\/api/, "");
      if (path !== "/chat") return json(base(path, init));
      const n = chats.push(String(init?.body));
      if (n === 1) await gate; // the first turn stays in flight until the test releases it
      return json({ answer: n === 1 ? "First." : "Second.", sources: [] });
    });
    renderAt("/", <Home />);
    await userEvent.click(await screen.findByRole("button", { name: "Ask the librarian" }));
    await userEvent.type(screen.getByPlaceholderText("Ask a question…"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    act(() => openChat({ mode: "explain", context: { path: "onboarding/README.md", title: "Onboarding", selection: "Hello governance." } }));
    expect(screen.getByText("About: Onboarding")).toBeInTheDocument(); // the context shows at once…
    expect(chats).toHaveLength(1); // …but nothing is sent over the turn in flight
    release();
    await screen.findByText("Second."); // the held action went out once the first turn had ended
    expect(screen.getByText("First.")).toBeInTheDocument();
    await waitFor(() => expect(chats).toHaveLength(2));
    expect(JSON.parse(chats[1])).toMatchObject({
      mode: "explain",
      message: "Explain this in plain language.",
      history: [{ role: "user", content: "hi" }, { role: "assistant", content: "First." }],
    });
  });

  it("drops a held toolbar action when the reader clears the context before the turn ends", async () => {
    stubReducedMotion();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const base = defaultResponder();
    const chats: string[] = [];
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/^\/api/, "");
      if (path !== "/chat") return json(base(path, init));
      if (chats.push(String(init?.body)) === 1) await gate;
      return json({ answer: "First.", sources: [] });
    });
    renderAt("/", <Home />);
    await userEvent.click(await screen.findByRole("button", { name: "Ask the librarian" }));
    await userEvent.type(screen.getByPlaceholderText("Ask a question…"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    act(() => openChat({ mode: "quiz", context: { path: "onboarding/README.md", title: "Onboarding", selection: "Hello governance." } }));
    await userEvent.click(screen.getByRole("button", { name: "Clear context" })); // changed their mind while it was held
    release();
    await screen.findByText("First.");
    await act(async () => {});
    expect(chats).toHaveLength(1); // the held quiz was never sent without its page
    expect(screen.queryByText("About: Onboarding")).toBeNull();
  });

  it("closes with the close button", async () => {
    stubReducedMotion();
    mockFetch(defaultResponder());
    renderAt("/", <Home />);
    await userEvent.click(screen.getByRole("button", { name: "Ask the librarian" }));
    await userEvent.click(screen.getByRole("button", { name: "Close chat" }));
    expect(screen.queryByRole("dialog", { name: "Ask the librarian" })).toBeNull();
  });
});
