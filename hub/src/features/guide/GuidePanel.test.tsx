import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Principal } from "../../api/types";
import { PRINCIPALS } from "../../api/mock/fixtures";
import { GuideProvider, useGuide } from "./GuideProvider";

vi.mock("../../auth/AuthProvider", () => ({
  CALLBACK_PATH: "/auth/callback",
  useAuth: () => ({
    snapshot: { status: "signed-in", accessToken: "t" },
    principal: current,
    personas: [],
    can: () => true,
    signIn: async () => {},
    signOut: async () => {},
  }),
}));
vi.mock("../../api", () => ({
  api: {
    briefs: { list: async () => [{ id: "b1", status: "draft", currentStep: "model", content: { useCase: { name: "Returns triage" } } }] },
    shelf: {
      list: async () => [
        {
          name: "x",
          stage: { label: "built" },
          youMaySign: ["owner"],
          status: "ready",
          version: "1.0.0",
          signoff: { owner: null, ai_security: null },
          recorded: {},
        },
      ],
    },
    requests: { list: async () => [] },
    guide: {
      ask: async (body: { question: string; audience: string; page: string }) => ({
        mode: "rules",
        audience: body.audience,
        answer: `From the repository's own pages:\n\nA sign-off is recorded by a named person.\n— CONTRIBUTING.md, Sign-offs`,
        sources: [{ id: "CONTRIBUTING.md#3", source: "CONTRIBUTING.md", title: "Contributing", section: "Sign-offs" }],
        suggestions: body.page === "/build/shelf/sign-offs" ? [] : [{ label: "The sign-off queue", route: "/build/shelf/sign-offs", why: "where they sign" }],
      }),
    },
  },
}));

let current: Principal = PRINCIPALS.gk;

function Where() {
  const { pathname } = useLocation();
  return <div data-testid="where">{pathname}</div>;
}
function Opener() {
  const g = useGuide();
  return (
    <button type="button" onClick={g.open}>
      open-guide
    </button>
  );
}

function mount(path = "/discover") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <GuideProvider>
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
          <Opener />
        </GuideProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the guide panel", () => {
  beforeEach(() => {
    localStorage.clear();
    current = PRINCIPALS.gk;
  });

  it("asks what the person is here for on first open, suggests from their role, and remembers the answer", async () => {
    current = PRINCIPALS.platform;
    mount();
    await userEvent.click(screen.getByRole("button", { name: "Open the guide" }));
    const aside = screen.getByRole("complementary", { name: "Guide" });
    expect(aside).toHaveTextContent("What brings you here?");
    const suggested = screen.getByRole("button", { name: /understand and decide/ });
    expect(suggested).toHaveClass("suggested");
    await userEvent.click(suggested);
    expect(aside).toHaveTextContent("Where you are");
    expect(aside).toHaveTextContent("Discover");
    expect(aside).toHaveTextContent("GA means signed and supported");
    expect(JSON.parse(localStorage.getItem("hub.guide.u_dr")!).persona).toBe("decide");
  });

  it("shows the next step from the hub's own facts, walks the person there, and tracks the path", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: "Open the guide" }));
    await userEvent.click(screen.getByRole("button", { name: /build something/ }));
    // A component waiting for this person's sign-off outranks orientation.
    await waitFor(() => expect(screen.getByLabelText("Suggested next step")).toHaveTextContent("1 component is waiting for your sign-off"));
    await userEvent.click(screen.getByRole("button", { name: /Open the queue/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/build/shelf/sign-offs");
    // The path reflects the visit and the draft brief the API reports.
    const steps = screen.getAllByRole("listitem");
    expect(steps.find((s) => s.textContent?.includes("Get it signed off"))).toHaveClass("done");
    expect(steps.find((s) => s.textContent?.includes("Write an intake brief"))).toHaveClass("done");
    expect(steps.find((s) => s.textContent?.includes("See what is on the shelf"))).toHaveClass("done");
    // A manual step is ticked by hand.
    const run = steps.find((s) => s.textContent?.includes("Run its five-minute example"))!;
    await userEvent.click(run.querySelector("input")!);
    expect(run).toHaveClass("done");
  });

  it("answers from the pages with sources and a place to go, and dismisses a nudge for good", async () => {
    mount("/learn");
    await userEvent.click(screen.getByRole("button", { name: "Open the guide" }));
    await userEvent.click(screen.getByRole("button", { name: /build something/ }));
    await userEvent.type(screen.getByLabelText("Your question"), "who signs a component off{enter}");
    await waitFor(() => expect(screen.getByLabelText("Ask the guide")).toHaveTextContent("A sign-off is recorded by a named person."));
    expect(screen.getByLabelText("Ask the guide")).toHaveTextContent("Sources");
    expect(screen.getByText(/CONTRIBUTING.md · Sign-offs/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /The sign-off queue/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/build/shelf/sign-offs");
    const nudgeBefore = screen.queryByLabelText("Suggested next step");
    if (nudgeBefore) {
      await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    }
    expect(JSON.parse(localStorage.getItem("hub.guide.u_gk")!).dismissed.length).toBe(nudgeBefore ? 1 : 0);
  });

  it("closes on Escape and stays off the sign-in page", async () => {
    mount("/signin");
    expect(screen.queryByRole("button", { name: "Open the guide" })).toBeNull();
    const view = mount("/workspace");
    await userEvent.click(view.getAllByRole("button", { name: "Open the guide" })[0]);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: "Guide" })).toBeNull();
  });
});
