/** Component-level coverage: markdown block types, tabs keyboard, modal focus trap, badges, formatting, storage fallbacks. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ApiError, readApiKey, storeApiKey } from "../api/client";
import { ActionsList } from "../components/AuditParts";
import { ReviewQueue } from "../components/AuditTrail";
import { StatusBadge } from "../components/Badges";
import ConfirmWithReason from "../components/ConfirmWithReason";
import LanguageSwitcher from "../components/LanguageSwitcher";
import Markdown from "../components/Markdown";
import { classifyLink } from "../components/markdownLinks";
import Tabs from "../components/Tabs";
import { formatDate, formatDay, formatMoney } from "../format";
import { changeLanguage, readStoredLanguage } from "../i18n";
import { audit } from "./harness";

afterEach(() => vi.restoreAllMocks());

const md = (source: string, plainLinks = false) =>
  render(<MemoryRouter><Markdown source={source} basePath="onboarding/README.md" plainLinks={plainLinks} catalogFiles={["onboarding/catalog.yaml"]} /></MemoryRouter>);

describe("Markdown blocks", () => {
  it("renders quotes, rules, nested lists, images, fences and centred tables", () => {
    md("> quoted *text*\n\n---\n\n- top\n  - nested\n1. first\n\n![diagram](img.png)\n\n~~~\ncode here\n~~~\n\n| h |\n|:-:|\n| c |\n\n***");
    expect(screen.getByText("quoted").tagName).toBe("BLOCKQUOTE");
    expect(document.querySelectorAll("hr").length).toBe(2);
    expect(screen.getByText("nested").closest("ul")?.className).toContain("list-[circle]");
    expect(screen.getByText("[diagram]")).toBeInTheDocument();
    expect(screen.getByText("code here").tagName).toBe("CODE");
    expect(screen.getByRole("columnheader", { name: "h" }).className).toContain("text-center");
  });

  it("routes file, anchor, protocol-relative and external links and can render links as text", () => {
    md("[cat](catalog.yaml) [other](other.yaml) [top](#top) [pr](//evil.example) [ext](https://example.com/a) [dir](../governance/)");
    expect(screen.getByRole("link", { name: "cat" })).toHaveAttribute("href", "/api/files/onboarding/catalog.yaml");
    expect(screen.queryByRole("link", { name: "other" })).toBeNull();
    expect(screen.getByRole("link", { name: "top" })).toHaveAttribute("href", "#top");
    expect(screen.queryByRole("link", { name: "pr" })).toBeNull();
    expect(screen.getByRole("link", { name: /ext .*opens an external site/ })).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByRole("link", { name: "dir" })).toHaveAttribute("href", "/kb/page/governance/README.md");
    md("[a](https://x.example) and [j](javascript:alert(1))", true);
    expect(screen.getByText("a (https://x.example)")).toBeInTheDocument();
    expect(screen.getByText("j")).toBeInTheDocument();
    expect(classifyLink("index.md", "   ")).toEqual({ kind: "inert" });
  });
});

describe("Tabs keyboard", () => {
  it("supports Home, End and ArrowLeft", async () => {
    const onChange = vi.fn();
    render(<Tabs tabs={[{ key: "a", label: "A" }, { key: "b", label: "B" }, { key: "c", label: "C" }]} current="b" label="sample" onChange={onChange}><p>panel</p></Tabs>);
    screen.getByRole("tab", { name: "B" }).focus();
    await userEvent.keyboard("{Home}");
    expect(onChange).toHaveBeenLastCalledWith("a");
    await userEvent.keyboard("{End}");
    expect(onChange).toHaveBeenLastCalledWith("c");
    await userEvent.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("a");
    await userEvent.keyboard("x");
    expect(onChange).toHaveBeenCalledTimes(3);
  });
});

describe("ConfirmWithReason modal", () => {
  it("traps Tab inside the dialog in both directions", async () => {
    render(<ConfirmWithReason title="T" description="D" token="GO" confirmLabel="Go" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Reason")).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText("Reason")).toHaveFocus();
  });
});

describe("audit parts", () => {
  it("shows rolled-back details and unknown severities", () => {
    const rolled = { ...audit().fixes_applied[0], rolled_back: true, rollback_forced: true, rollback_reason: "owner asked", rollback_timestamp: "2026-09-15T11:00:00Z" };
    render(<MemoryRouter><ActionsList actions={[rolled]} auditId="audit-1" canRollback /><ReviewQueue items={[{ path: "x.md", reason: "r", severity: "odd", at: "2026-09-15T10:00:00Z" }]} /></MemoryRouter>);
    expect(screen.getByText(/owner asked/)).toBeInTheDocument();
    expect(screen.getByText("forced")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Roll back" })).toBeNull();
    expect(screen.getByText("odd")).toBeInTheDocument();
    render(<StatusBadge status="weird" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});

describe("formatting fallbacks", () => {
  it("handles invalid locales and dates", () => {
    expect(formatMoney(1.5, "not a locale")).toBe("$1.50");
    expect(formatDate("nonsense", "en")).toBe("nonsense");
    expect(formatDate(null, "en")).toBe("");
    expect(formatDate("2026-09-15T10:00:00Z", "not a locale")).toContain("2026");
    expect(formatDay("2026-09-01", "en")).toMatch(/2026/);
    expect(formatDay("bad", "en")).toBe("bad");
    expect(formatDay(null, "en")).toBe("");
    expect(formatDay("2026-09-01", "not a locale")).toBe("2026-09-01");
  });
});

describe("storage fallbacks", () => {
  it("survives a throwing localStorage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readApiKey()).toBe("");
    storeApiKey("k");
    expect(readStoredLanguage()).toBe("en");
    await changeLanguage("es");
    expect(document.documentElement.getAttribute("lang")).toBe("es");
    await changeLanguage("en");
    expect(new ApiError(500, "x").name).toBe("ApiError");
  });

  it("switches language from the select", async () => {
    render(<LanguageSwitcher />);
    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");
    expect(document.documentElement.getAttribute("lang")).toBe("fr");
    await changeLanguage("en");
  });
});
