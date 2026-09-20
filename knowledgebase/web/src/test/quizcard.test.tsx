import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { openChat, resetChatBus } from "../chatBus";
import Home from "../pages/Home";
import { defaultResponder, mockFetch, profile, renderAt, signedIn, type Responder } from "./harness";

const stubReducedMotion = () =>
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} }));

const QUIZ = {
  answer: "",
  sources: [{ path: "onboarding/README.md", title: "Onboarding" }],
  quiz: [
    { q: "Which page is linked?", options: ["governance", "billing"], answer: 0, why: "It links to governance." },
    { q: "What is the page's status?", options: ["draft", "active", "deprecated"], answer: 1, why: "" },
  ],
};
const CONTEXT = { path: "onboarding/README.md", title: "Onboarding", selection: "Healthy page. Links to governance." };
const RECORDED = { path: "onboarding/README.md", score: 1, total: 2, at: "2026-09-18T10:00:00Z" };

/** Home with the chat widget, a quiz already asked for `CONTEXT` and answered by the fake API. */
async function openQuiz(responder: Responder) {
  stubReducedMotion();
  const calls = mockFetch(responder);
  renderAt("/", <Home />);
  await screen.findByRole("heading", { level: 1 });
  act(() => openChat({ mode: "quiz", context: CONTEXT }));
  await screen.findByText("1. Which page is linked?");
  return calls;
}

const answer = async (first: string, second: string) => {
  await userEvent.click(screen.getByRole("radio", { name: first }));
  await userEvent.click(screen.getByRole("radio", { name: second }));
  await userEvent.click(screen.getByRole("button", { name: "Check answers" }));
};

afterEach(() => {
  vi.unstubAllGlobals();
  resetChatBus();
});

describe("QuizCard", () => {
  it("grades locally, explains each answer, and records the tally for a signed-in reader", async () => {
    const calls = await openQuiz(defaultResponder({ "/me": signedIn, "/profile": profile, "/chat": QUIZ, "/profile/quizzes": RECORDED }));
    expect(screen.getByText("Quiz me on this.")).toBeInTheDocument(); // the reader's turn
    expect(screen.getAllByText("“Healthy page. Links to governance.”")).toHaveLength(2); // under the turn and in the chip
    expect(screen.getByText("About: Onboarding")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check answers" })).toBeDisabled(); // until every question is answered
    await answer("billing", "active");
    expect(screen.getByText("You got 1 of 2 right.")).toBeInTheDocument();
    expect(screen.getByText("✗ Incorrect")).toBeInTheDocument();
    expect(screen.getByText("— It links to governance.")).toBeInTheDocument();
    expect(screen.getByText("✓ Correct")).toBeInTheDocument();
    expect(screen.getAllByRole("radio").every((r) => (r as HTMLInputElement).disabled)).toBe(true);
    expect(await screen.findByText("Result saved to your profile.")).toBeInTheDocument();
    const post = calls.find((c) => c.path === "/profile/quizzes");
    expect(post?.init?.method).toBe("POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ path: "onboarding/README.md", score: 1, total: 2 });
    await userEvent.click(screen.getByRole("button", { name: "Close chat" })); // the graded quiz survives closing the panel
    await userEvent.click(screen.getByRole("button", { name: "Ask the librarian" }));
    expect(screen.getByText("You got 1 of 2 right.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check answers" })).toBeNull();
    expect(calls.filter((c) => c.path === "/profile/quizzes")).toHaveLength(1);
  });

  it("records nothing for an anonymous reader and offers no explanation when everything is right", async () => {
    const calls = await openQuiz(defaultResponder({ "/chat": QUIZ }));
    await answer("governance", "active");
    expect(screen.getByText("You got 2 of 2 right.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Explain what I got wrong" })).toBeNull();
    expect(calls.some((c) => c.path === "/profile/quizzes")).toBe(false);
  });

  it("asks the librarian to explain the missed questions, as a plain question with the same context", async () => {
    let chats = 0;
    const base = defaultResponder({ "/chat": QUIZ });
    const calls = await openQuiz((path, init) => (path === "/chat" && ++chats > 1 ? { answer: "Because the page links to governance.", sources: [] } : base(path, init)));
    await answer("billing", "active");
    await userEvent.click(screen.getByRole("button", { name: "Explain what I got wrong" }));
    expect(await screen.findByText("Because the page links to governance.")).toBeInTheDocument();
    const posts = calls.filter((c) => c.path === "/chat");
    expect(posts).toHaveLength(2);
    const body = JSON.parse(String(posts[1].init?.body));
    expect(body.mode).toBeUndefined();
    expect(body.context).toEqual(CONTEXT);
    expect(body.history).toEqual([{ role: "user", content: "Quiz me on this." }]); // the quiz turn itself has no text
    expect(body.message).toBe(
      "Explain why the right answers to these questions are right:\n1. Which page is linked? — I chose “billing”; the right answer is “governance”.",
    );
  });
});
