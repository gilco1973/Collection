import type { GuideAudience, Principal } from "../../api/types";
import { ROUTES } from "../../routes";

/**
 * The guide's pure logic: who it is talking to, what it knows about them, the
 * path it walks them along, and the one next step it suggests on each page.
 *
 * Nothing here reads the network or the DOM. The provider gathers `Facts`
 * from the hub's own queries (briefs, the shelf, requests, the principal) and
 * from what the person has visited; these functions turn them into steps and
 * nudges. Every claim in a step or a nudge is something the hub's pages state.
 */

/** What the person told the guide they are here for. */
export type Persona = "build" | "decide" | "use";

export const PERSONAS: Array<{ key: Persona; title: string; sub: string; audience: GuideAudience }> = [
  { key: "build", title: "I'm here to build something", sub: "an engineer or AI champion with an initiative in mind", audience: "engineer" },
  { key: "decide", title: "I'm here to understand and decide", sub: "a leader who needs to know what this is and what it cannot do", audience: "leadership" },
  { key: "use", title: "I'm here to use the hub", sub: "find an assistant, ask a question, request access", audience: "employee" },
];

export const audienceOf = (p: Persona): GuideAudience => PERSONAS.find((x) => x.key === p)?.audience ?? "engineer";

/** A default from the principal, offered on first open; the person confirms or changes it. */
export function suggestedPersona(p: Principal | undefined): Persona {
  if (!p) return "build";
  if (p.roles.includes("platform.lead") || (p.teams.some((t) => t.lead) && !p.roles.includes("ops.investigator"))) return "decide";
  if (!p.roles.length) return "use";
  return "build";
}

/** What the guide knows, gathered by the provider from the hub's own state. */
export interface Facts {
  persona: Persona;
  page: string;
  visited: string[];
  /** Steps the person ticked themselves (for the ones no record can confirm). */
  ticked: string[];
  dismissed: string[];
  asked: number;
  toursDone: string[];
  briefs: { drafts: number; filed: number; draftName?: string; draftId?: string; draftStep?: string };
  shelf: { total: number; onShelf: number; waitingForMe: number };
  requests: { pending: number };
  isSigner: boolean;
}

export const EMPTY_FACTS: Facts = {
  persona: "build",
  page: "/",
  visited: [],
  ticked: [],
  dismissed: [],
  asked: 0,
  toursDone: [],
  briefs: { drafts: 0, filed: 0 },
  shelf: { total: 0, onShelf: 0, waitingForMe: 0 },
  requests: { pending: 0 },
  isSigner: false,
};

const REFERENCE_AGENT = "/discover/agents/incident-first-read-agent";
const EMPLOYEE_ASSISTANT = "/assistant/employee-assistant";

const visited = (f: Facts, route: string) => f.visited.some((v) => v === route || v.startsWith(`${route}/`) || v.startsWith(`${route}?`));

export interface Step {
  id: string;
  title: string;
  why: string;
  route?: string;
  /** A question the guide answers instead of a page to open. */
  ask?: string;
  /** Shown as a command for the person to run; the step is ticked by hand. */
  command?: string;
  done: (f: Facts) => boolean;
  /** The person may tick it themselves. */
  manual?: boolean;
}

export type StepState = "done" | "on" | "todo";

const JOURNEYS: Record<Persona, Step[]> = {
  build: [
    {
      id: "b.shelf",
      title: "See what is on the shelf",
      why: "Six kinds of component; the tabs split them by what they are for.",
      route: ROUTES.discover,
      done: (f) => visited(f, ROUTES.discover),
    },
    {
      id: "b.agent",
      title: "Open the reference agent",
      why: "A template, three tools and the harness. Its listing shows exactly what it may read and do.",
      route: REFERENCE_AGENT,
      done: (f) => visited(f, REFERENCE_AGENT),
    },
    {
      id: "b.run",
      title: "Run its five-minute example",
      why: "One command; it reads, asks before a write, and stops when told. Tick this when it ran.",
      command: "cd components/agents/incident-first-read-agent && python3 example.py",
      route: REFERENCE_AGENT,
      manual: true,
      done: (f) => f.ticked.includes("b.run"),
    },
    {
      id: "b.brief",
      title: "Write an intake brief",
      why: "One page in six sections; it saves as you go and shows an estimate and a road as you fill it.",
      route: ROUTES.intake,
      done: (f) => f.briefs.drafts + f.briefs.filed > 0,
    },
    {
      id: "b.file",
      title: "File the brief with your lead",
      why: "Filing needs a lead's confirmation of the road; the brief then goes to the registry.",
      route: ROUTES.intake,
      done: (f) => f.briefs.filed > 0,
    },
    {
      id: "b.build",
      title: "Build from components",
      why: "Copy a component's directory; it imports nothing outside it. Tick this when your first one is in.",
      route: ROUTES.discover,
      manual: true,
      done: (f) => f.ticked.includes("b.build"),
    },
    {
      id: "b.onboard",
      title: "Take your component to the shelf",
      why: "Six stages from scaffolded to on the shelf; the tracker shows where each one is.",
      route: ROUTES.shelfOnboarding,
      done: (f) => visited(f, ROUTES.shelfOnboarding),
    },
    {
      id: "b.sign",
      title: "Get it signed off",
      why: "The owner and an AI security engineer sign the version; the commit is the signature.",
      route: ROUTES.shelfSignoffs,
      done: (f) => visited(f, ROUTES.shelfSignoffs),
    },
  ],
  decide: [
    {
      id: "d.what",
      title: "What this is, in five minutes",
      why: "The roads, the collection and the programme, on one page.",
      route: ROUTES.learn,
      done: (f) => visited(f, ROUTES.learn),
    },
    {
      id: "d.cannot",
      title: "What an agent cannot do",
      why: "A listing's permission table is the whole list. Nothing outside it can run.",
      route: REFERENCE_AGENT,
      done: (f) => visited(f, REFERENCE_AGENT),
    },
    {
      id: "d.controls",
      title: "The controls, in plain terms",
      why: "Ask, and the answer comes from our own documentation with its sources.",
      ask: "What stops an agent doing something we did not ask for?",
      done: (f) => f.ticked.includes("d.controls"),
    },
    {
      id: "d.signers",
      title: "Who signs, and what they attest",
      why: "Two named people per version. A change makes the signature stale.",
      route: ROUTES.shelfSignoffs,
      done: (f) => visited(f, ROUTES.shelfSignoffs),
    },
    {
      id: "d.cost",
      title: "What it costs and who uses it",
      why: "Usage is shown back per person and cost centre.",
      route: ROUTES.workspace,
      done: (f) => visited(f, ROUTES.workspace),
    },
    {
      id: "d.decisions",
      title: "The decisions that are yours",
      why: "The programme page lists what is open and who owns each one. Tick this when you have read them.",
      route: ROUTES.learn,
      manual: true,
      done: (f) => f.ticked.includes("d.decisions"),
    },
    {
      id: "d.walk",
      title: "Ask for a walkthrough",
      why: "Anything the pages do not answer, the programme lead answers in person. Tick this once it is booked.",
      manual: true,
      done: (f) => f.ticked.includes("d.walk"),
    },
  ],
  use: [
    {
      id: "u.find",
      title: "Find what you may use",
      why: "The catalog shows what your role opens; the rest can be requested.",
      route: ROUTES.discover,
      done: (f) => visited(f, ROUTES.discover),
    },
    {
      id: "u.ask",
      title: "Ask the employee assistant",
      why: "It reads pages and cites them. It has no tools, so it cannot act on anything.",
      route: EMPLOYEE_ASSISTANT,
      done: (f) => visited(f, ROUTES.assistant),
    },
    {
      id: "u.request",
      title: "Request access to something",
      why: "From a listing; your requests and their state are in your workspace.",
      route: ROUTES.workspace,
      done: (f) => f.requests.pending > 0 || visited(f, ROUTES.workspace),
    },
    {
      id: "u.feedback",
      title: "Say whether an answer helped",
      why: "Every answer has a thumbs up and down; that is how the pages get better. Tick this once you have.",
      route: EMPLOYEE_ASSISTANT,
      manual: true,
      done: (f) => f.ticked.includes("u.feedback"),
    },
  ],
};

export function journey(f: Facts): Array<Step & { state: StepState }> {
  const steps = JOURNEYS[f.persona];
  let onSeen = false;
  return steps.map((s) => {
    if (s.done(f)) return { ...s, state: "done" };
    if (!onSeen) {
      onSeen = true;
      return { ...s, state: "on" };
    }
    return { ...s, state: "todo" };
  });
}

/* ---------- Where you are ---------- */

export interface PageNote {
  title: string;
  note: Record<Persona, string>;
}

const PAGE_NOTES: Array<[RegExp, PageNote]> = [
  [
    /^\/discover\/agents\//,
    {
      title: "An agent's listing",
      note: {
        build: "Everything the agent may read and do is in the table below the summary, with its tier. The evidence links open the tests and the walkthrough.",
        decide: "The permission table is the whole list. Reads run; a write waits for a person; money needs two. Nothing outside the table can run.",
        use: "This listing tells you what the agent does and whether your role may open it. If not, request access from here.",
      },
    },
  ],
  [
    /^\/discover\//,
    {
      title: "A listing",
      note: {
        build: "What it is, what it needs, and its sign-off state. Copy the directory named under 'Where it lives'.",
        decide: "What this is for, who owns it, and who signed it. Two names and a version, or it is not on the shelf.",
        use: "What it does and whether you may use it. Access is decided by your role, never by asking nicely.",
      },
    },
  ],
  [
    /^\/discover/,
    {
      title: "Discover",
      note: {
        build: "The catalog. The tabs split it by kind; the collection's components sit under their kind with a stage chip.",
        decide: "Everything the bank has, by kind. GA means signed and supported; preview means still earning its sign-offs.",
        use: "Everything you may open, and what you may ask for. Search with ⌘K.",
      },
    },
  ],
  [
    /^\/assistant/,
    {
      title: "The employee assistant",
      note: {
        build: "The reference for a grounded assistant: every claim carries a citation or is dropped. The sources are listed under each answer.",
        decide: "It answers from the bank's pages and shows which ones. It has no tools: it cannot change anything, anywhere.",
        use: "Ask in plain words. Every answer names the page it came from; say whether it helped.",
      },
    },
  ],
  [
    /^\/workspace/,
    {
      title: "My workspace",
      note: {
        build: "What you use, what your team is building, your requests, and the playground key for the gateway.",
        decide: "Usage per person and cost centre, and what each team is building. Nothing runs outside a budget.",
        use: "Your assistants, your requests and their state, and your usage.",
      },
    },
  ],
  [
    /^\/build\/intake/,
    {
      title: "The intake brief",
      note: {
        build: "One page in six sections. It saves as you go and estimates cost and a road from what you write; your lead confirms the road when you file.",
        decide: "Every initiative starts as one of these. The road it lands on decides which controls apply before anything is built.",
        use: "This is where engineers propose a new use of AI. If you have an idea, your team's champion writes it up here.",
      },
    },
  ],
  [
    /^\/build\/shelf\/sign-offs/,
    {
      title: "Sign-offs",
      note: {
        build: "The queue. Each component needs the owner and an AI security engineer at its current version; the form records what they attest.",
        decide: "Two named people per version, each attesting they ran the tests, ran the example and read the rules. A change makes it stale.",
        use: "Where the engineers sign the components off. Nothing here needs you.",
      },
    },
  ],
  [
    /^\/build\/shelf\/onboarding/,
    {
      title: "Onboarding",
      note: {
        build: "Where each component stands on its six stages, and what a new champion does in the first week.",
        decide: "The state of the shelf at a glance: how many are signed, how many are waiting, and on whom.",
        use: "The engineers' checklist for bringing a component in. Nothing here needs you.",
      },
    },
  ],
  [
    /^\/learn/,
    {
      title: "Learn",
      note: {
        build: "The six roads, the collection with each component's stage, and the programme's cadence.",
        decide: "Start here: the roads say what kind of AI is allowed to do what; the programme section lists what is open and who decides it.",
        use: "What the roads mean, and where the office hours are.",
      },
    },
  ],
  [
    /^\/settings/,
    {
      title: "Settings",
      note: {
        build: "Theme, density, accessibility and notifications.",
        decide: "Theme, density, accessibility and notifications.",
        use: "Theme, density, accessibility and notifications.",
      },
    },
  ],
];

export function pageNote(page: string): PageNote {
  for (const [re, note] of PAGE_NOTES) if (re.test(page)) return note;
  return {
    title: "The hub",
    note: {
      build: "Discover, My workspace, Build and Learn.",
      decide: "Discover, My workspace, Build and Learn.",
      use: "Discover, My workspace, Build and Learn.",
    },
  };
}

/* ---------- The one next step ---------- */

export interface Nudge {
  id: string;
  text: string;
  cta?: { label: string; route?: string; ask?: string; tour?: string };
}

/** The best next step for this page and these facts, or none. Dismissed nudges never return; the order is the priority. */
export function nudge(f: Facts): Nudge | undefined {
  const p = f.page;
  const on = (re: RegExp) => re.test(p);
  const candidates: Array<[boolean, Nudge]> = [
    [
      f.shelf.waitingForMe > 0 && !on(/^\/build\/shelf\/sign-offs/),
      {
        id: `sign.${f.shelf.waitingForMe}`,
        text: `${f.shelf.waitingForMe} component${f.shelf.waitingForMe === 1 ? " is" : "s are"} waiting for your sign-off.`,
        cta: { label: "Open the queue", route: ROUTES.shelfSignoffs },
      },
    ],
    [
      f.briefs.drafts > 0 && !on(/^\/build\/intake/),
      {
        id: `draft.${f.briefs.draftId ?? "x"}`,
        text: `Your brief “${f.briefs.draftName || "Untitled brief"}” is waiting${f.briefs.draftStep ? ` at ${f.briefs.draftStep}` : ""}.`,
        cta: { label: "Continue the brief", route: f.briefs.draftId ? `${ROUTES.intake}/${f.briefs.draftId}` : ROUTES.intake },
      },
    ],
    [
      f.persona === "build" && on(/^\/discover$/) && !visited(f, REFERENCE_AGENT),
      {
        id: "build.agent",
        text: "The shortest way to see what an agent, its tools and the harness look like is the reference agent's listing.",
        cta: { label: "Open the reference agent", route: REFERENCE_AGENT },
      },
    ],
    [
      f.persona === "build" && on(/^\/discover\/agents\/incident-first-read-agent/),
      {
        id: "build.run",
        text: "Run its five-minute example: it reads, asks before a write, and stops when told. Everything in the table below has a test.",
        cta: { label: "Show me the command", ask: "How do I run the reference agent's example?" },
      },
    ],
    [
      f.persona === "build" && on(/^\/build\/intake/) && f.briefs.drafts + f.briefs.filed === 0,
      {
        id: "build.brief",
        text: "Start with the use case's name and who it is for. The brief saves as you go; nothing is lost if you leave.",
        cta: { label: "Walk me through it", tour: "build" },
      },
    ],
    [
      f.persona === "build" && on(/^\/learn/),
      {
        id: "build.collection",
        text: "The collection section lists every component with its stage. Skills need nothing installed; everything else copies as a directory.",
        cta: { label: "See the components", route: `${ROUTES.learn}#collection` },
      },
    ],
    [
      f.persona === "decide" && on(/^\/discover\/agents\//),
      {
        id: "decide.table",
        text: "The table under “What it can read and do” is the entire permission list. A read runs; a write waits for a person; money needs two people. Nothing else can run.",
        cta: { label: "What else stops it?", ask: "What stops an agent doing something we did not ask for?" },
      },
    ],
    [
      f.persona === "decide" && on(/^\/discover$/),
      {
        id: "decide.ga",
        text: "GA on a card means two named people signed that version. Preview means it is still earning them. Nothing here runs without a sign-off you can read.",
        cta: { label: "See who signs", route: ROUTES.shelfSignoffs },
      },
    ],
    [
      f.persona === "decide" && on(/^\/build\/shelf\/sign-offs/),
      {
        id: "decide.signers",
        text: "Each sign-off records four attestations: tests green, example run, walkthrough read, rules read. A new version makes it stale until both sign again.",
        cta: { label: "What do they attest?", ask: "What does a sign-off attest?" },
      },
    ],
    [
      f.persona === "decide" && on(/^\/workspace/),
      {
        id: "decide.usage",
        text: "Usage is shown back per person and cost centre, and the playground key is rotated here. Nothing runs against a budget it does not have.",
        cta: { label: "What does it cost?", ask: "What does the platform cost to run?" },
      },
    ],
    [
      f.persona === "decide" && on(/^\/assistant/),
      {
        id: "decide.assistant",
        text: "This assistant has no tools. It reads pages, cites them, and drops any sentence it cannot cite. It cannot change anything.",
        cta: { label: "How does it answer?", ask: "How does the employee assistant answer a question?" },
      },
    ],
    [
      f.persona === "decide" && on(/^\/learn/) && !f.ticked.includes("d.decisions"),
      {
        id: "decide.open",
        text: "The programme section lists the decisions that are open and who owns each. Three of them are yours.",
        cta: { label: "Show me around", tour: "decide" },
      },
    ],
    [
      f.persona === "use" && on(/^\/discover/),
      {
        id: "use.assistant",
        text: "The employee assistant answers from the bank's pages and shows which ones. Ask it anything you would ask a colleague.",
        cta: { label: "Ask it something", route: EMPLOYEE_ASSISTANT },
      },
    ],
    [
      f.persona === "use" && on(/^\/assistant/),
      {
        id: "use.feedback",
        text: "Every answer names the page it came from. The thumbs under an answer are how the pages get better.",
        cta: { label: "Where are my requests?", route: ROUTES.workspace },
      },
    ],
    [
      !f.toursDone.includes(f.persona) && f.asked === 0,
      {
        id: `tour.${f.persona}`,
        text: "Want the two-minute tour? I'll point at the parts of the hub that matter for you, page by page.",
        cta: { label: "Show me around", tour: f.persona },
      },
    ],
  ];
  // Work waiting on the person comes first for a builder; a leader hears about the page they are on first.
  const ordered = f.persona === "decide" ? [...candidates.slice(2), ...candidates.slice(0, 2)] : candidates;
  for (const [when, n] of ordered) if (when && !f.dismissed.includes(n.id)) return n;
  return undefined;
}

/** Before the person has said what they are here for: one invitation, once. */
export const WELCOME: Nudge = {
  id: "welcome",
  text: "New here? Tell me what you're here for and I'll point you at the pages that matter, and answer from our own documentation.",
  cta: { label: "Start" },
};

/* ---------- Starter questions ---------- */

export const STARTERS: Record<Persona, string[]> = {
  build: [
    "How do I run the reference agent's example?",
    "What does a component need before it can be signed off?",
    "How do I use a component from the shelf?",
    "What does the harness enforce?",
  ],
  decide: [
    "What stops an agent doing something we did not ask for?",
    "Can an agent move money on its own?",
    "Who signs a component off, and what do they attest?",
    "What happens if the model makes a mistake?",
  ],
  use: ["What can the employee assistant answer?", "How do I request access to an assistant?", "Where do I see my usage?", "Can I turn AI assistance off?"],
};

/* ---------- Tours ---------- */

export interface TourStep {
  route: string;
  target: string;
  title: string;
  body: string;
}

export const TOURS: Record<string, { title: string; steps: TourStep[] }> = {
  build: {
    title: "The hub for a builder",
    steps: [
      {
        route: ROUTES.discover,
        target: "discover-tabs",
        title: "The catalog, by kind",
        body: "Assistants, agents, knowledge, tools and roads. The collection's components sit under their kind with a stage chip.",
      },
      {
        route: REFERENCE_AGENT,
        target: "listing-catalog",
        title: "What an agent may do",
        body: "Every tool with its tier. R runs; W1 waits for a person; W2 and money need two. This table is the whole list.",
      },
      {
        route: ROUTES.intake,
        target: "intake-form",
        title: "The intake brief",
        body: "Six sections, saved as you go. The estimate and the road update as you write; your lead confirms the road when you file.",
      },
      {
        route: ROUTES.shelfOnboarding,
        target: "onboarding-tracker",
        title: "The way to the shelf",
        body: "Six stages per component. Yours starts at scaffolded and ends with two signatures.",
      },
      {
        route: ROUTES.shelfSignoffs,
        target: "signoff-queue",
        title: "The sign-off queue",
        body: "The owner and an AI security engineer sign each version here. The export hands it to the shelf tool; the commit is the signature.",
      },
    ],
  },
  decide: {
    title: "The hub for a decision",
    steps: [
      {
        route: ROUTES.learn,
        target: "learn-roads",
        title: "Six roads",
        body: "Each road says what kind of AI may do what, and which controls apply. An initiative is placed on one before anything is built.",
      },
      {
        route: REFERENCE_AGENT,
        target: "listing-catalog",
        title: "What an agent cannot do",
        body: "This table is the entire permission list. Reads run; a write waits for a named person; money needs two. Nothing outside it can run.",
      },
      {
        route: ROUTES.shelfSignoffs,
        target: "signoff-queue",
        title: "Who signs",
        body: "Two named people per version, each attesting four things. A change makes the signature stale until they sign again.",
      },
      {
        route: ROUTES.workspace,
        target: "workspace-usage",
        title: "What it costs",
        body: "Usage is shown back per person and cost centre. Nothing runs against a budget it does not have.",
      },
      {
        route: ROUTES.assistant,
        target: "assistant-composer",
        title: "An assistant with no tools",
        body: "It reads pages and cites them. Any sentence it cannot cite is dropped. It cannot change anything.",
      },
    ],
  },
  use: {
    title: "The hub for everyday use",
    steps: [
      {
        route: ROUTES.discover,
        target: "discover-tabs",
        title: "What you may use",
        body: "Your role decides what opens. Anything else can be requested from its listing.",
      },
      {
        route: ROUTES.assistant,
        target: "assistant-composer",
        title: "Ask in plain words",
        body: "The assistant answers from the bank's pages and names them. Say whether the answer helped.",
      },
      { route: ROUTES.workspace, target: "workspace-requests", title: "Your requests", body: "Everything you asked for and where it stands." },
    ],
  },
};
