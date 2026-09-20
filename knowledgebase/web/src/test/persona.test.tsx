/** Persona-driven console: picker, Home cards and section order, Browse split, role-based menu. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PageSummary } from "../api/types";
import Browse from "../pages/Browse";
import Home from "../pages/Home";
import Settings from "../pages/Settings";
import { defaultResponder, me, mockFetch, page, profile, renderAt, signedIn, viewer, type Responder } from "./harness";

afterEach(() => vi.unstubAllGlobals());

const governance = page({ path: "governance/README.md", title: "Governance", section: "governance", audience: ["engineer"] });

/** A signed-in reader with the given persona; `/pages?audience=…` answers with `forYou`, everything else as usual. */
function withPersona(persona: string | null, forYou: PageSummary[] = [], extra: Record<string, unknown> = {}): Responder {
  const base = defaultResponder({ "/me": signedIn, "/profile": { ...profile, persona }, "/profile/persona": { ...profile, persona: "engineer" }, ...extra });
  return (path, init) => (path.startsWith("/pages?audience=") ? { items: forYou } : base(path, init));
}

describe("PersonaPicker", () => {
  it("saves the chosen persona to the profile and marks it selected", async () => {
    const calls = mockFetch(withPersona(null));
    renderAt("/settings", <Settings />);
    const engineer = await screen.findByRole("button", { name: "Engineer" });
    expect(engineer).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "No persona" })).toHaveAttribute("aria-pressed", "true"); // Settings has no skip flow
    await userEvent.click(engineer);
    await waitFor(() => expect(calls.some((c) => c.path === "/profile/persona" && c.init?.method === "PUT")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.path === "/profile/persona")?.init?.body))).toEqual({ persona: "engineer" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Engineer" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "No persona" })).toHaveAttribute("aria-pressed", "false");
  });

  it("clears the persona with the none option and shows the save error", async () => {
    const calls = mockFetch(withPersona("engineer", [], { "/profile/persona": new Response(JSON.stringify({ error: { code: "x", message: "profile down" } }), { status: 500 }) }));
    renderAt("/settings", <Settings />);
    await userEvent.click(await screen.findByRole("button", { name: "No persona" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/profile/persona" && c.init?.method === "PUT")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.path === "/profile/persona")?.init?.body))).toEqual({ persona: null });
    expect(await screen.findByRole("alert")).toHaveTextContent("profile down");
  });

  it("is absent for anonymous readers and on servers without single sign-on", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/settings", <Settings />);
    await screen.findByText("Single sign-on is not configured on this server.");
    expect(screen.queryByTestId("persona-picker")).toBeNull();
    expect(screen.queryByText("Persona")).toBeNull();
  });
});

describe("Home", () => {
  it("asks a signed-in reader without a persona to choose one, and skip hides the card without a request", async () => {
    const calls = mockFetch(withPersona(null));
    renderAt("/", <Home />);
    const card = await screen.findByTestId("persona-choose");
    expect(screen.getByRole("heading", { name: "Choose your persona" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "New hire" })).toBeInTheDocument();
    const skip = within(card).getByRole("button", { name: "Skip for now" });
    expect(skip).not.toHaveAttribute("aria-pressed"); // a dismiss action, not a toggle state
    await userEvent.click(skip);
    expect(screen.queryByTestId("persona-choose")).toBeNull();
    expect(calls.some((c) => c.init?.method === "PUT")).toBe(false);
    expect(screen.queryByTestId("persona-for-you")).toBeNull();
  });

  it("shows the for-you card, counts and reorders the sections, and lets the reader change persona", async () => {
    const calls = mockFetch(withPersona("engineer", [governance]));
    renderAt("/", <Home />);
    expect(await screen.findByRole("heading", { name: "For you — Engineer" })).toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith("/pages?audience=engineer"))).toBe(true);
    expect(within(await screen.findByTestId("for-you")).getByRole("link", { name: "Governance" })).toHaveAttribute("href", "/kb/page/governance/README.md");
    const sections = within(await screen.findByTestId("sections")).getAllByRole("link");
    expect(sections.map((l) => l.textContent?.slice(0, 10))).toEqual(["Governance", "Onboarding"]);
    expect(sections[0]).toHaveTextContent("1 for you");
    expect(sections[1]).not.toHaveTextContent("for you");
    expect(screen.queryByTestId("persona-choose")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Change persona" }));
    expect(within(screen.getByTestId("persona-for-you")).getByRole("button", { name: "Engineer" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the empty state when nothing is written for the persona", async () => {
    mockFetch(withPersona("new-hire"));
    renderAt("/", <Home />);
    expect(await screen.findByText("No pages are written for this persona yet.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "For you — New hire" })).toBeInTheDocument();
  });

  it("shows no persona UI to an anonymous reader", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/", <Home />);
    await screen.findByText("Onboarding");
    expect(screen.queryByTestId("persona-choose")).toBeNull();
    expect(screen.queryByTestId("persona-for-you")).toBeNull();
  });
});

describe("Browse", () => {
  const leadership = page({ path: "onboarding/leaders.md", title: "For leaders", audience: ["leadership"] });
  const shared = page({ path: "onboarding/all.md", title: "For all", audience: ["everyone"] });

  it("splits a section into pages for the persona (or everyone) and dimmed other audiences", async () => {
    mockFetch(withPersona("new-hire", [], { "/sections/onboarding/pages": { items: [page(), leadership, shared] } }));
    renderAt("/kb/onboarding", <Browse />, undefined, "/kb/:section");
    const mine = await screen.findByTestId("for-you");
    expect(within(mine).getAllByRole("link").map((l) => l.textContent)).toEqual(["Onboarding", "For all"]);
    expect(screen.getByRole("heading", { name: "For you — New hire" })).toBeInTheDocument();
    const others = screen.getByTestId("other-audiences");
    expect(within(others).getAllByRole("link").map((l) => l.textContent)).toEqual(["For leaders"]);
    expect(others).toHaveClass("opacity-70");
    expect(screen.getByRole("heading", { name: "Other audiences" })).toBeInTheDocument();
  });

  it("keeps a single undivided list without a persona", async () => {
    mockFetch(withPersona(null, [], { "/sections/onboarding/pages": { items: [page(), leadership] } }));
    renderAt("/kb/onboarding", <Browse />, undefined, "/kb/:section");
    expect(await screen.findByRole("link", { name: "For leaders" })).toBeInTheDocument();
    expect(screen.queryByTestId("for-you")).toBeNull();
    expect(screen.queryByTestId("other-audiences")).toBeNull();
  });
});

describe("Role-based menu", () => {
  it("hides the Audits link from viewers and fits the mobile bar to four links", async () => {
    mockFetch(defaultResponder({ "/me": viewer }));
    renderAt("/", <Home />);
    await screen.findByText("Viewer");
    expect(screen.queryByRole("link", { name: "Audits" })).toBeNull();
    expect(screen.getAllByRole("link", { name: "Browse" }).length).toBe(2); // desktop and mobile bars
    expect(document.querySelector("nav.fixed")).toHaveClass("grid-cols-4");
  });

  it("shows the Audits link to operators in both bars", async () => {
    mockFetch(defaultResponder({ "/me": me }));
    renderAt("/", <Home />);
    await screen.findByText("Operator");
    expect(screen.getAllByRole("link", { name: "Audits" }).length).toBe(2);
    expect(document.querySelector("nav.fixed")).toHaveClass("grid-cols-5");
  });
});
