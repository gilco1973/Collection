import { useMutation, useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api";
import type { GuideAnswer } from "../../api/types";
import { CALLBACK_PATH, useAuth } from "../../auth/AuthProvider";
import { track } from "../../telemetry";
import { openRolesFor } from "../shelf/stages";
import { GuideLauncher } from "./GuideLauncher";
import { GuidePanel } from "./GuidePanel";
import { audienceOf, EMPTY_FACTS, journey, nudge, suggestedPersona, TOURS, WELCOME, type Facts, type Nudge, type Persona } from "./model";
import { Tour } from "./Tour";
import "./guide.css";

/**
 * The guide: a companion that knows who it is talking to, where they are, what
 * they have done, and what the collection's pages say.
 *
 * State that is the person's own (their persona, what they have visited and
 * ticked, which nudges they dismissed) lives in the browser under their
 * principal id. Everything factual (briefs, the shelf, requests) is read from
 * the hub's own queries, so the guide never contradicts the page beside it.
 * Answers come from `POST /guide/ask`, which quotes the repository's pages and
 * names them; the guide never invents a sentence about the platform.
 */

const STEP_TITLES: Record<string, string> = {
  useCase: "the use case",
  people: "people and channel",
  dataAndTools: "data and tools",
  model: "the model",
  outcome: "the outcome",
  review: "review",
};

interface Stored {
  persona?: Persona;
  visited: string[];
  ticked: string[];
  dismissed: string[];
  asked: number;
  toursDone: string[];
}
const EMPTY: Stored = { visited: [], ticked: [], dismissed: [], asked: 0, toursDone: [] };
const key = (id: string) => `hub.guide.${id}`;

function load(id: string): Stored {
  try {
    const raw = localStorage.getItem(key(id));
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<Stored>) } : EMPTY;
  } catch {
    return EMPTY;
  }
}
function save(id: string, s: Stored) {
  try {
    localStorage.setItem(key(id), JSON.stringify(s));
  } catch {
    /* private mode or quota: the guide still works for the session */
  }
}

export interface Exchange {
  id: number;
  question: string;
  answer?: GuideAnswer;
  error?: string;
}

export interface GuideApi {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  facts: Facts;
  persona: Persona | undefined;
  suggested: Persona;
  /** Undefined asks again on next open. */
  setPersona: (p: Persona | undefined) => void;
  nudge: Nudge | undefined;
  dismiss: (id: string) => void;
  tick: (stepId: string, on: boolean) => void;
  go: (route: string) => void;
  ask: (question: string) => void;
  asking: boolean;
  exchanges: Exchange[];
  clearExchanges: () => void;
  startTour: (id: string) => void;
  tour: { id: string; step: number } | undefined;
  tourNext: () => void;
  tourBack: () => void;
  tourEnd: () => void;
}

const Ctx = createContext<GuideApi | null>(null);

export function useGuide(): GuideApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useGuide outside GuideProvider");
  return v;
}

const HIDDEN_ON = ["/signin", "/403", CALLBACK_PATH];

export function GuideProvider({ children }: { children: ReactNode }) {
  const { principal, snapshot } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const page = location.pathname;
  const signedIn = snapshot.status === "signed-in" && !!principal;
  const pid = principal?.id ?? "";

  const [stored, setStored] = useState<Stored>(EMPTY);
  const [isOpen, setOpen] = useState(false);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [tour, setTour] = useState<{ id: string; step: number } | undefined>();
  const seq = useRef(0);

  // One store per person: load on sign-in, forget on sign-out.
  useEffect(() => {
    setStored(pid ? load(pid) : EMPTY);
    setExchanges([]);
    setTour(undefined);
  }, [pid]);

  const update = useCallback(
    (fn: (s: Stored) => Stored) => {
      setStored((s) => {
        const next = fn(s);
        if (pid) save(pid, next);
        return next;
      });
    },
    [pid],
  );

  // What the person has seen: the guide's own record, kept as routes.
  useEffect(() => {
    if (!pid || HIDDEN_ON.includes(page)) return;
    update((s) => (s.visited.includes(page) ? s : { ...s, visited: [...s.visited, page].slice(-200) }));
  }, [page, pid, update]);

  // The facts: from the hub's own queries, only once signed in.
  const briefs = useQuery({ queryKey: ["briefs"], queryFn: ({ signal }) => api.briefs.list(signal), enabled: signedIn, staleTime: 30_000 });
  const shelf = useQuery({ queryKey: ["shelf"], queryFn: ({ signal }) => api.shelf.list(signal), enabled: signedIn, staleTime: 30_000 });
  const requests = useQuery({ queryKey: ["requests"], queryFn: ({ signal }) => api.requests.list(signal), enabled: signedIn, staleTime: 30_000 });

  const suggested = useMemo(() => suggestedPersona(principal), [principal]);
  const persona = stored.persona;

  const facts = useMemo<Facts>(() => {
    const drafts = (briefs.data ?? []).filter((b) => b.status === "draft");
    const filed = (briefs.data ?? []).filter((b) => b.status !== "draft");
    const draft = drafts[0];
    const entries = shelf.data ?? [];
    return {
      ...EMPTY_FACTS,
      persona: persona ?? suggested,
      page,
      visited: stored.visited,
      ticked: stored.ticked,
      dismissed: stored.dismissed,
      asked: stored.asked,
      toursDone: stored.toursDone,
      briefs: {
        drafts: drafts.length,
        filed: filed.length,
        draftName: draft?.content.useCase.name,
        draftId: draft?.id,
        draftStep: draft ? STEP_TITLES[draft.currentStep] : undefined,
      },
      shelf: {
        total: entries.length,
        onShelf: entries.filter((e) => e.stage.label === "on the shelf").length,
        waitingForMe: entries.filter((e) => openRolesFor(e).length > 0).length,
      },
      requests: { pending: (requests.data ?? []).filter((r) => r.status === "pending").length },
      isSigner: entries.some((e) => e.youMaySign.length > 0),
    };
  }, [briefs.data, shelf.data, requests.data, persona, suggested, page, stored]);

  const current = useMemo(() => (persona ? nudge(facts) : stored.dismissed.includes(WELCOME.id) ? undefined : WELCOME), [facts, persona, stored.dismissed]);

  const askMutation = useMutation({
    mutationFn: (q: string) => api.guide.ask({ question: q, audience: audienceOf(facts.persona), page }),
  });

  const ask = useCallback(
    (question: string) => {
      const q = question.trim();
      if (!q) return;
      const id = ++seq.current;
      setExchanges((x) => [...x, { id, question: q }]);
      track("guide.ask", { persona: facts.persona, page, len: q.length });
      askMutation.mutate(q, {
        onSuccess: (answer) => {
          setExchanges((x) => x.map((e) => (e.id === id ? { ...e, answer } : e)));
          update((s) => {
            const ticked = /stops an agent/i.test(q) && !s.ticked.includes("d.controls") ? [...s.ticked, "d.controls"] : s.ticked;
            return { ...s, asked: s.asked + 1, ticked };
          });
        },
        onError: (e: unknown) =>
          setExchanges((x) => x.map((ex) => (ex.id === id ? { ...ex, error: e instanceof Error ? e.message : "The guide could not answer." } : ex))),
      });
    },
    [askMutation, facts.persona, page, update],
  );

  const open = useCallback(() => {
    setOpen(true);
    track("guide.open", { page });
  }, [page]);
  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((o) => !o), []);
  const setPersona = useCallback(
    (p: Persona | undefined) => {
      update((s) => ({ ...s, persona: p }));
      track("guide.persona", { persona: p ?? "reset" });
    },
    [update],
  );
  const dismiss = useCallback((id: string) => update((s) => ({ ...s, dismissed: [...s.dismissed, id] })), [update]);
  const tick = useCallback(
    (stepId: string, on: boolean) => update((s) => ({ ...s, ticked: on ? [...new Set([...s.ticked, stepId])] : s.ticked.filter((t) => t !== stepId) })),
    [update],
  );
  const go = useCallback(
    (route: string) => {
      const [path, hash] = route.split("#");
      navigate(hash ? { pathname: path, hash: `#${hash}` } : path);
      if (hash) window.setTimeout(() => document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    },
    [navigate],
  );

  const startTour = useCallback((id: string) => {
    if (!TOURS[id]) return;
    setOpen(false);
    setTour({ id, step: 0 });
    track("guide.tour", { id });
  }, []);
  const tourEnd = useCallback(() => {
    setTour((t) => {
      if (t) update((s) => ({ ...s, toursDone: [...new Set([...s.toursDone, t.id])] }));
      return undefined;
    });
  }, [update]);
  const tourNext = useCallback(() => {
    setTour((t) => {
      if (!t) return t;
      if (t.step + 1 >= TOURS[t.id].steps.length) {
        update((s) => ({ ...s, toursDone: [...new Set([...s.toursDone, t.id])] }));
        return undefined;
      }
      return { ...t, step: t.step + 1 };
    });
  }, [update]);
  const tourBack = useCallback(() => setTour((t) => (t && t.step > 0 ? { ...t, step: t.step - 1 } : t)), []);

  // Alt+G opens the guide anywhere; Escape closes it (the tour handles its own).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && e.key.toLowerCase() === "g") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo<GuideApi>(
    () => ({
      isOpen,
      open,
      close,
      toggle,
      facts,
      persona,
      suggested,
      setPersona,
      nudge: current,
      dismiss,
      tick,
      go,
      ask,
      asking: askMutation.isPending,
      exchanges,
      clearExchanges: () => setExchanges([]),
      startTour,
      tour,
      tourNext,
      tourBack,
      tourEnd,
    }),
    [
      isOpen,
      open,
      close,
      toggle,
      facts,
      persona,
      suggested,
      setPersona,
      current,
      dismiss,
      tick,
      go,
      ask,
      askMutation.isPending,
      exchanges,
      startTour,
      tour,
      tourNext,
      tourBack,
      tourEnd,
    ],
  );

  const shown = signedIn && !HIDDEN_ON.includes(page);
  const steps = useMemo(() => (persona ? journey(facts) : []), [facts, persona]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {shown && !tour && <GuideLauncher />}
      {shown && isOpen && !tour && <GuidePanel steps={steps} />}
      {shown && tour && <Tour id={tour.id} step={tour.step} onNext={tourNext} onBack={tourBack} onEnd={tourEnd} navigate={go} />}
    </Ctx.Provider>
  );
}
