import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import PageView from "../pages/PageView";
import { setContentLanguage } from "../contentLanguage";
import { defaultResponder, detail, errorResponse, mockFetch, renderAt } from "./harness";

afterEach(() => {
  vi.unstubAllGlobals();
  setContentLanguage("en");
});

describe("PageView", () => {
  it("renders markdown, metadata, findings and sends a problem report", async () => {
    const calls = mockFetch(defaultResponder({ "/pages/onboarding/README.md/reports": { id: "problem-1", owner: "enablement" } }));
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    expect((await screen.findAllByRole("heading", { name: "Onboarding", level: 1 })).length).toBe(1);
    expect(screen.getByRole("link", { name: "governance" })).toHaveAttribute("href", "/kb/page/governance/README.md");
    expect(screen.getByText("code")).toBeInTheDocument();
    expect(screen.getByText("broken link")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Tell the owner what you found"), "This page is out of date.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Thanks. The owner (enablement) has been notified.")).toBeInTheDocument();
    const post = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ category: "outdated", message: "This page is out of date." });
  });

  it("withholds sensitive pages and shows frontmatter errors", async () => {
    mockFetch(defaultResponder({ "/pages/onboarding/README.md": { ...detail, withheld: true, body_markdown: null, meta: { ...detail.meta, frontmatter_error: "bad yaml", stale: true } } }));
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    expect(await screen.findByText("Content withheld pending review")).toBeInTheDocument();
    expect(screen.getByText("This page's metadata is invalid: bad yaml")).toBeInTheDocument();
    expect(screen.getByText("Past review window")).toBeInTheDocument();
  });

  it("shows an error for a missing page", async () => {
    mockFetch(defaultResponder({ "/pages/nope.md": errorResponse(404, "no page at 'nope.md'") }));
    renderAt("/kb/page/nope.md", <PageView />, undefined, "/kb/page/*");
    expect(await screen.findByText("no page at 'nope.md'")).toBeInTheDocument();
  });

  it("switches to a translated page, and falls back to English with a notice when none exists yet", async () => {
    mockFetch(
      defaultResponder({
        "/pages/onboarding/README.md?lang=es": {
          ...detail,
          translated: true,
          meta: { ...detail.meta, title: "Inicio" },
          body_markdown: "# Inicio\n\nContenido.\n",
        },
      }),
    );
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    await screen.findByRole("heading", { name: "Onboarding", level: 1 });
    await userEvent.selectOptions(screen.getByLabelText("Content language"), "es");
    expect(await screen.findByRole("heading", { name: "Inicio", level: 1 })).toBeInTheDocument();
    expect(screen.queryByText("Not yet translated into this language; showing English.")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Content language"), "he");
    expect(await screen.findByText("Not yet translated into this language; showing English.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Onboarding", level: 1 })).not.toHaveAttribute("dir", "rtl");
  });

  it("renders a translated Hebrew page right-to-left", async () => {
    mockFetch(
      defaultResponder({
        "/pages/onboarding/README.md?lang=he": { ...detail, translated: true, meta: { ...detail.meta, title: "התחלה" } },
      }),
    );
    renderAt("/kb/page/onboarding/README.md", <PageView />, undefined, "/kb/page/*");
    await userEvent.selectOptions(await screen.findByLabelText("Content language"), "he");
    expect(await screen.findByRole("heading", { name: "התחלה", level: 1 })).toHaveAttribute("dir", "rtl");
  });
});
