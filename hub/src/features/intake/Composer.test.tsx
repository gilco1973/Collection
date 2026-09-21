import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BriefContent } from "../../api/schemas";
import { DRAFT_BRIEF, REGISTRY_SYSTEMS, REGISTRY_TOOLS } from "../../api/mock/fixtures";
import { Composer, reusesOf } from "./Composer";
import type { BriefState } from "./useBrief";

vi.mock("../../api", () => ({
  api: {
    registry: { systems: async () => REGISTRY_SYSTEMS, tools: async () => REGISTRY_TOOLS },
    catalog: {
      get: async () => ({
        listings: [
          {
            id: "governed-action-loop",
            name: "Governed action loop",
            kind: "tool",
            road: "R1",
            lifecycle: "preview",
            collection: true,
            description: "the loop an agent runs inside",
          },
          { id: "employee-assistant", name: "Employee assistant", kind: "assistant", road: "R2", lifecycle: "GA", description: "reads pages" },
          { id: "r2-template", name: "R2 template", kind: "road", road: "R2", lifecycle: "GA", description: "a road" },
        ],
      }),
    },
  },
}));

/** A drag in jsdom: the DataTransfer the browser would carry, by hand. */
function dataTransfer() {
  const store: Record<string, string> = {};
  return {
    setData: (k: string, v: string) => {
      store[k] = v;
    },
    getData: (k: string) => store[k] ?? "",
    get types() {
      return Object.keys(store);
    },
    effectAllowed: "all",
    dropEffect: "none",
  };
}

function mount(overrides: Partial<BriefContent["dataAndTools"]> = {}) {
  const content: BriefContent = { ...DRAFT_BRIEF.content, dataAndTools: { systems: [], tools: [], dataClasses: ["internal"], tierCeiling: "R", ...overrides } };
  const update = vi.fn();
  const onClose = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Composer s={{ update } as unknown as BriefState} content={content} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { update, onClose, content };
}

describe("the intake composer", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists what exists in four groups and marks a system without a contract as not usable", async () => {
    mount();
    const dialog = await screen.findByRole("dialog", { name: "Compose from what exists" });
    await waitFor(() => expect(dialog).toHaveTextContent("Systems of record"));
    expect(dialog).toHaveTextContent("Tools");
    expect(dialog).toHaveTextContent("The collection");
    expect(dialog).toHaveTextContent("The bank's services");
    expect(dialog).toHaveTextContent("Governed action loop");
    expect(dialog).not.toHaveTextContent("R2 template"); // a road is not a capability to reuse
    const crm = await screen.findByTestId("item-system-crm-service");
    expect(crm).toHaveAttribute("aria-disabled", "true");
    expect(crm).toHaveTextContent("no recorded contract yet");
    expect(crm.querySelector("button")).toBeDisabled();
  });

  it("drops a tool onto the brief and brings its system with it", async () => {
    const { update } = mount();
    const item = await screen.findByTestId("item-tool-cos_get_case");
    const dt = dataTransfer();
    fireEvent.dragStart(item, { dataTransfer: dt });
    expect(dt.getData("application/x-hub-item")).toContain("cos_get_case");
    const zone = screen.getByTestId("dropzone");
    fireEvent.dragOver(zone, { dataTransfer: dt });
    expect(zone).toHaveClass("over");
    fireEvent.drop(zone, { dataTransfer: dt });
    expect(update).toHaveBeenCalledWith("dataAndTools", {
      tools: [{ name: "cos_get_case", tier: "R", classes: ["confidential"] }],
      systems: [{ id: "cos-case-notes", name: "COS · case notes" }],
    });
    expect(screen.getByRole("dialog")).toHaveTextContent("cos_get_case brought COS · case notes with it");
  });

  it("adds a component and a service as reuse with the Add button, and a disabled system not at all", async () => {
    const { update } = mount();
    await userEvent.click(await screen.findByRole("button", { name: "Add Governed action loop" }));
    expect(update).toHaveBeenLastCalledWith("dataAndTools", { reuses: [{ id: "governed-action-loop", name: "Governed action loop", kind: "component" }] });
    await userEvent.click(screen.getByRole("button", { name: "Add Employee assistant" }));
    expect(update).toHaveBeenLastCalledWith("dataAndTools", { reuses: [{ id: "employee-assistant", name: "Employee assistant", kind: "service" }] });
    const dt = dataTransfer();
    fireEvent.dragStart(screen.getByTestId("item-system-crm-service"), { dataTransfer: dt });
    fireEvent.drop(screen.getByTestId("dropzone"), { dataTransfer: dt });
    expect(update).toHaveBeenCalledTimes(2);
  });

  it("shows the consequences and offers the fix: the ceiling a W1 tool needs, the classes the tools read", async () => {
    const { update } = mount({
      tools: [
        { name: "cos_reverse_fee", tier: "W1", classes: ["internal"] },
        { name: "cos_get_case", tier: "R", classes: ["confidential"] },
      ],
      dataClasses: ["internal"],
      tierCeiling: "R",
    });
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("the ceiling is Read, which does not cover it");
    await userEvent.click(screen.getByRole("button", { name: "Set the ceiling to Write with confirmation" }));
    expect(update).toHaveBeenLastCalledWith("dataAndTools", { tierCeiling: "W1" });
    await userEvent.click(screen.getByRole("button", { name: "Tick confidential" }));
    expect(update).toHaveBeenLastCalledWith("dataAndTools", { dataClasses: ["internal", "confidential"] });
    expect(dialog).toHaveTextContent("A write profile: your team lead files the brief");
    expect(dialog).toHaveTextContent("13 tools left under the session ceiling");
    // Items already in the brief are marked and not draggable.
    const inBrief = screen.getByTestId("item-tool-cos_get_case");
    expect(inBrief).toHaveTextContent("in the brief");
    expect(inBrief).toHaveAttribute("draggable", "false");
  });

  it("refuses a money tool for a first consumer and removes from the brief in place", async () => {
    const { update } = mount({ tools: [{ name: "ledger_post", tier: "M", classes: ["internal"] }], systems: [{ id: "ledger", name: "General ledger" }] });
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("a money tool is refused for a first consumer");
    await userEvent.click(screen.getByRole("button", { name: "Remove ledger_post" }));
    expect(update).toHaveBeenLastCalledWith("dataAndTools", { tools: [] });
    await userEvent.click(screen.getByRole("button", { name: "General ledger · remove" }));
    expect(update).toHaveBeenLastCalledWith("dataAndTools", { systems: [] });
  });

  it("closes on Done and on Escape, and reads reuses defensively", async () => {
    const { onClose } = mount();
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(reusesOf({ systems: [], tools: [], dataClasses: [], tierCeiling: "R" })).toEqual([]);
  });
});

describe("the harness baseline in the composer", () => {
  it("shows the harness set locked with any tool, marks it required in the palette, and never lets it be removed", async () => {
    mount({ tools: [{ name: "cos_get_case", tier: "R", classes: ["confidential"] }], systems: [{ id: "cos-case-notes", name: "COS · case notes" }] });
    const dialog = await screen.findByRole("dialog");
    const baseline = await screen.findByTestId("baseline");
    expect(baseline).toHaveTextContent("Governed action loop");
    expect(baseline).toHaveTextContent("Audit chain");
    expect(baseline.querySelectorAll('[aria-label="required, cannot be removed"]')).toHaveLength(5);
    expect(screen.queryByRole("button", { name: "Governed action loop · remove" })).toBeNull();
    expect(dialog).toHaveTextContent("Every tool runs inside the governed action loop");
    // In the palette the component reads as required, not as a thing to add.
    const item = await screen.findByTestId("item-component-governed-action-loop");
    expect(item).toHaveTextContent("required");
    expect(screen.queryByRole("button", { name: "Add Governed action loop" })).toBeNull();
  });

  it("shows no baseline until a tool is in the brief", async () => {
    mount();
    await screen.findByRole("dialog");
    expect(screen.queryByTestId("baseline")).toBeNull();
    expect(await screen.findByRole("button", { name: "Add Governed action loop" })).toBeInTheDocument();
  });
});
