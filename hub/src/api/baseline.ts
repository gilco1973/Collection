import type { BriefContent } from "./schemas";

/**
 * The harness baseline: what every AI solution that calls a tool runs inside,
 * whether or not the person thought to name it. The rule is the collection's,
 * not the form's: an agent's manifest requires a harness, so a brief that
 * names tools carries the harness set as required reuses. The intake adds
 * them, the composer shows them locked, filing writes them, and hub-api
 * applies the same rule on its side, so the API cannot file a brief without
 * them (`services/hub-api/hubapi/briefs.py`, BASELINE).
 */
export interface BaselineEntry {
  id: string;
  name: string;
  kind: "component";
  required: true;
  /** One line a leader can read: why this comes with every tool. */
  why: string;
}

export const BASELINE: BaselineEntry[] = [
  {
    id: "governed-action-loop",
    name: "Governed action loop",
    kind: "component",
    required: true,
    why: "the loop every tool call runs inside: three fixed hooks, tiers, budgets, kill switches",
  },
  {
    id: "untrusted-input-guard",
    name: "Untrusted input guard",
    kind: "component",
    required: true,
    why: "text the model reads is evidence, never an instruction; a tainted session is capped at reads",
  },
  {
    id: "cited-llm-engine",
    name: "Cited LLM engine",
    kind: "component",
    required: true,
    why: "every claim carries a citation or is dropped; a malformed answer is refused",
  },
  {
    id: "audit-chain",
    name: "Audit chain",
    kind: "component",
    required: true,
    why: "every step lands on a hash-chained record that cannot be edited without the edit showing",
  },
  { id: "ids-only-logging", name: "Ids-only logging", kind: "component", required: true, why: "logs carry ids and routes, never a person's data" },
];

/** The MCP tool server is offered, not imposed: a brief's channels are people's; an AI client reaches the tools through it. */
export const MCP_BASELINE: BaselineEntry = {
  id: "mcp-tool-server",
  name: "MCP tool server",
  kind: "component",
  required: true,
  why: "AI clients reach the tools only through the harness, over MCP",
};

export const BASELINE_WHY = "Every tool runs inside the governed action loop; the guard, the engine, the chain and ids-only logging come with it.";

export type ReuseEntry = { id: string; name: string; kind: string; required?: boolean };

/** The baseline a brief needs: nothing without tools; the harness set with any tool. */
export function baselineFor(content: Pick<BriefContent, "dataAndTools">): BaselineEntry[] {
  return content.dataAndTools.tools.length ? BASELINE : [];
}

/** The brief's reuses with the baseline merged in and marked required; the person's own choices are kept. */
export function withBaseline(content: BriefContent): BriefContent {
  const needed = baselineFor(content);
  const own = ((content.dataAndTools as { reuses?: ReuseEntry[] }).reuses ?? []).filter((r) => !needed.some((b) => b.id === r.id));
  const reuses = [...needed.map(({ id, name, kind, required }) => ({ id, name, kind, required })), ...own];
  if (!needed.length && !own.length) return content;
  return { ...content, dataAndTools: { ...content.dataAndTools, reuses } as BriefContent["dataAndTools"] };
}

/** Baseline entries a brief with tools still lacks; the form adds them, the server refuses to file without them. */
export function missingBaseline(content: Pick<BriefContent, "dataAndTools">): BaselineEntry[] {
  const have = new Set(((content.dataAndTools as { reuses?: ReuseEntry[] }).reuses ?? []).map((r) => r.id));
  return baselineFor(content).filter((b) => !have.has(b.id));
}
