import type { GuideAnswer, GuideAudience, GuideSuggestion } from "../types";
import { COLLECTION_GUIDE, type GuidePassage } from "./guide";

/**
 * The guide's rules mode, in the browser, over the same corpus the hub-api
 * serves (`data/guide-corpus.json` and this file's `guide.ts` are both written
 * by `tools/shelf.py --write`). It mirrors `hubapi/guide.py`: a question is
 * screened for instructions, the passages are ranked with BM25, and the answer
 * is the best passages themselves with their sources, never a sentence the hub
 * made up. The model mode lives only in the service, behind the bank's gateway.
 */

const STOP = new Set(
  "the and for that this with are you how what can does from into its our your will one not have has was which when where who why about there here they them than then also each every some any all but use used using want need help please me do did doing done something anything thing things is it in on to of a an be by or as at if we my i".split(
    " ",
  ),
);

const SYNONYMS: Record<string, string[]> = {
  stop: ["kill", "switch", "tier", "confirmation", "refuse"],
  prevent: ["tier", "confirmation", "structural"],
  block: ["tier", "confirmation", "refuse"],
  control: ["tier", "confirmation", "harness", "policy"],
  controls: ["tier", "confirmation", "harness", "policy"],
  safe: ["tier", "confirmation", "structural", "harness"],
  safety: ["tier", "confirmation", "structural", "harness"],
  risk: ["tier", "threat", "control"],
  money: ["money", "tier", "dual"],
  harm: ["undo", "tier", "kill"],
  wrong: ["undo", "audit", "verification"],
  mistake: ["undo", "audit", "verification"],
  hallucinate: ["cite", "citation", "drop"],
  trust: ["cite", "audit", "sign-off"],
  proof: ["audit", "chain", "record"],
  record: ["audit", "chain"],
  approve: ["confirmation", "sign-off"],
  approval: ["confirmation", "sign-off"],
  permission: ["confirmation", "tier", "entitlement"],
  password: ["credential", "secret"],
  secret: ["credential", "secretsbyname"],
  cost: ["usage", "budget", "spend"],
  price: ["usage", "budget"],
  ask: ["confirmation", "confirm"],
  own: ["autonomous", "confirmation"],
  bot: ["agent", "assistant"],
  start: ["five-minute", "example", "onboarding"],
  begin: ["five-minute", "example", "onboarding"],
  install: ["five-minute", "vendored", "copy"],
  deploy: ["deploy", "docker", "bundle", "configuration"],
};
const EXPANSION_WEIGHT = 0.6;

export function tokens(text: string): string[] {
  const out: string[] = [];
  for (const m of text.toLowerCase().matchAll(/[a-z0-9][a-z0-9\-.]+/g)) {
    let w = m[0].replace(/^[.-]+|[.-]+$/g, "");
    if (w.length < 2 || STOP.has(w)) continue;
    if (w.length > 4 && w.endsWith("s")) w = w.slice(0, -1);
    out.push(w);
  }
  return out;
}

/** What reads as an instruction rather than a question. The service scores with the harness's guard; this is the same idea, smaller. */
const INSTRUCTION =
  /ignore (all |any |the )?(previous|prior|above|earlier) (instructions?|prompts?)|system prompt|you are now|disregard (your|the) (rules|instructions)|reveal (your|the) (prompt|instructions)|pretend (you|to be)/i;

class Corpus {
  private tf: Map<string, number>[] = [];
  private df = new Map<string, number>();
  private dl: number[] = [];
  private avgdl = 1;
  constructor(
    readonly passages: GuidePassage[],
    private k1 = 1.5,
    private b = 0.75,
  ) {
    for (const x of passages) {
      const t = tokens(`${x.title} ${x.section} ${x.text}`);
      const counts = new Map<string, number>();
      for (const w of t) counts.set(w, (counts.get(w) ?? 0) + 1);
      this.tf.push(counts);
      this.dl.push(t.length);
      for (const w of counts.keys()) this.df.set(w, (this.df.get(w) ?? 0) + 1);
    }
    this.avgdl = passages.length ? this.dl.reduce((a, b) => a + b, 0) / passages.length : 1;
  }

  search(query: string, audience?: GuideAudience, k = 5): Array<[number, GuidePassage]> {
    const own = tokens(query);
    if (!own.length) return [];
    const q = new Map<string, number>(own.map((w) => [w, 1]));
    for (const w of own) for (const e of SYNONYMS[w] ?? []) if (!q.has(e)) q.set(e, EXPANSION_WEIGHT);
    const n = Math.max(1, this.passages.length);
    const scored: Array<[number, GuidePassage]> = [];
    this.passages.forEach((x, i) => {
      let s = 0;
      for (const [w, weight] of q) {
        const f = this.tf[i].get(w) ?? 0;
        if (!f) continue;
        const df = this.df.get(w) ?? 0;
        const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
        s += (weight * idf * (f * (this.k1 + 1))) / (f + this.k1 * (1 - this.b + (this.b * this.dl[i]) / this.avgdl));
      }
      if (s <= 0) return;
      if (audience && x.audience.includes(audience)) s *= 1.25;
      const head = tokens(`${x.title} ${x.section}`);
      if (own.some((w) => head.includes(w))) s *= 1.15;
      scored.push([s, x]);
    });
    scored.sort((a, b) => b[0] - a[0]);
    return scored.slice(0, k);
  }
}

let corpus: Corpus | undefined;
const getCorpus = () => (corpus ??= new Corpus(COLLECTION_GUIDE));

/** Where the hub can walk a person to, by what they ask about. First match wins; the page they are on is never suggested. */
export const ROUTE_SUGGESTIONS: Array<[RegExp, string, string, string]> = [
  [
    /sign(ed|s)?[- ]?off|attest|who signs|approve a component/,
    "/build/shelf/sign-offs",
    "The sign-off queue",
    "where the owner and an AI security engineer sign a component",
  ],
  [
    /onboard|stage|way to the shelf|first week|champion/,
    "/build/shelf/onboarding",
    "The onboarding tracker",
    "where each component is and what a champion does first",
  ],
  [/brief|propose|intake|new use case|start (a|an) (initiative|project)/, "/build/intake", "The intake brief", "one page in six sections; it saves as you go"],
  [
    /first[- ]read|incident|reference agent|example agent|template/,
    "/discover/agents/incident-first-read-agent",
    "The reference agent",
    "a template, three tools and the harness; every rule has a test",
  ],
  [/cost|usage|budget|spend|charge/, "/workspace", "My workspace", "usage shown back per person and cost centre"],
  [/assistant|ask a question|chat|cite|citation/, "/assistant/employee-assistant", "The employee assistant", "reads pages and cites them; it has no tools"],
  [/programme|program|meeting|cadence|paved road|learn|practice/, "/learn", "Learn", "the roads, the collection and the programme"],
  [/component|shelf|tool|integration|skill|pattern|reuse|copy/, "/discover", "Discover", "the catalog: assistants, agents, knowledge, tools and roads"],
];

export function suggestions(question: string, page?: string): GuideSuggestion[] {
  const q = question.toLowerCase();
  for (const [pattern, route, label, why] of ROUTE_SUGGESTIONS) if (pattern.test(q) && route !== page) return [{ label, route, why }];
  return [];
}

const LEAD: Record<GuideAudience, string> = {
  engineer: "From the repository's own pages:",
  leadership: "Here is what our own documentation says, in plain terms.",
  employee: "Here is what the hub's pages say:",
};
const GAP: Record<GuideAudience, string> = {
  engineer: "I couldn't find that in the collection's pages. Try naming the component or the page, or ask in the programme's office hours.",
  leadership:
    "I couldn't find that in our own documentation, so I won't guess. The programme lead can answer it directly, or it can go on the open-decisions list.",
  employee: "I couldn't find that in the hub's pages. The employee assistant may have it, or your team lead can point you to the right place.",
};

/** Markdown from the pages, as prose: table rows become "a · b · c", separators and emphasis go, bullets stay readable. */
export function plain(md: string): string {
  return md
    .split("\n")
    .filter((l) => !/^\s*\|?\s*:?-{3,}/.test(l))
    .map((l) => {
      const t = l.trim();
      if (t.startsWith("|"))
        return (
          t
            .replace(/^\||\|$/g, "")
            .split("|")
            .map((c) => c.trim())
            .filter(Boolean)
            .join(" · ") + "."
        );
      return t
        .replace(/^#{1,6}\s+/, "")
        .replace(/^[-*]\s+/, "• ")
        .replace(/^\d+\.\s+/, (m) => m);
    })
    .join("\n")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
}

function trim(text: string, n = 520): string {
  const t = plain(text).replace(/\s+/g, " ").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(". "), cut.lastIndexOf(" ")) + 1).trim()}…`;
}

export function ask(question: string, audience: GuideAudience = "engineer", page?: string): GuideAnswer {
  const q = question.trim();
  const base = { mode: "rules" as const, audience, suggestions: suggestions(q, page) };
  if (!q) return { ...base, answer: "Ask me anything about the collection, the hub or the programme.", sources: [], refused: "empty" };
  if (INSTRUCTION.test(q))
    return {
      ...base,
      answer:
        "That reads as an instruction rather than a question, so I won't act on it. Ask me what you want to know and I will answer from the collection's own pages.",
      sources: [],
      refused: "taint",
      suggestions: [],
    };
  const hits = getCorpus().search(q, audience, 3);
  if (!hits.length) return { ...base, answer: GAP[audience], sources: [] };
  const answer = [LEAD[audience], ...hits.map(([, x]) => `${trim(x.text)}\n— ${x.title}, ${x.section}`)].join("\n\n");
  return { ...base, answer, sources: hits.map(([, x]) => ({ id: x.id, source: x.source, title: x.title, section: x.section })) };
}
