/** Voice input: hidden without SpeechRecognition, dictates and wires into Home + Search. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";
import VoiceInputButton from "../components/VoiceInputButton";
import Search from "../pages/Search";
import { defaultResponder, mockFetch, renderAt } from "./harness";

class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = "";
  interimResults = false;
  maxAlternatives = 1;
  onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start() {
    FakeRecognition.instances.push(this);
  }
  stop() {
    this.onend?.();
  }
}

const renderApp = (path: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>
    </QueryClientProvider>,
  );

afterEach(() => {
  vi.unstubAllGlobals();
  FakeRecognition.instances = [];
});

describe("VoiceInputButton", () => {
  it("renders nothing where the browser has no SpeechRecognition", () => {
    render(<VoiceInputButton onResult={() => {}} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("listens, reports the transcript, and returns to idle", async () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    const onResult = vi.fn();
    render(<VoiceInputButton onResult={onResult} />);
    await userEvent.click(screen.getByRole("button", { name: "Search by voice" }));
    const button = await screen.findByRole("button", { name: "Listening…" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    FakeRecognition.instances[0].onresult?.({ results: [{ 0: { transcript: "gateway policy" } }] });
    expect(onResult).toHaveBeenCalledWith("gateway policy");
    FakeRecognition.instances[0].onend?.();
    expect(await screen.findByRole("button", { name: "Search by voice" })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("voice input on the console", () => {
  it("dictates into the home search box and navigates to results", async () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    mockFetch(defaultResponder());
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Search by voice" }));
    FakeRecognition.instances[0].onresult?.({ results: [{ 0: { transcript: "gateway" } }] });
    expect(await screen.findByPlaceholderText("Search pages…")).toHaveValue("gateway");
  });

  it("dictates into the search page's query box", async () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    mockFetch(defaultResponder());
    renderAt("/search", <Search />);
    await userEvent.click(await screen.findByRole("button", { name: "Search by voice" }));
    FakeRecognition.instances[0].onresult?.({ results: [{ 0: { transcript: "onboarding" } }] });
    await waitFor(() => expect(screen.getByPlaceholderText("Search pages…")).toHaveValue("onboarding"));
  });
});
