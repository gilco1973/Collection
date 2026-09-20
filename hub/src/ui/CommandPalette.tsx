import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { ConsumerSummary } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { assistantRoute, consumerRoute, ROUTES } from "../routes";
import { track } from "../telemetry";
import { Glyph, Search } from "./icons";

/**
 * ⌘K: search assistants, tools and knowledge, and jump anywhere in the Hub.
 * Results come from `GET /catalog/search`, so they are already filtered to
 * what this person may see. A free-text query that matches nothing is offered
 * to the employee assistant as a question.
 */
interface PaletteApi {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}
const Ctx = createContext<PaletteApi | null>(null);

export function usePalette(): PaletteApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePalette outside PaletteProvider");
  return v;
}

export function PaletteProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const value = useMemo(() => ({ open, close, isOpen }), [open, close, isOpen]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {isOpen && <Palette onClose={close} />}
    </Ctx.Provider>
  );
}

type Item = { id: string; title: string; small?: string; glyph?: ConsumerSummary["glyph"]; run: () => void };

function Palette({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const { snapshot, signOut } = useAuth();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const signedIn = snapshot.status === "signed-in";

  const search = useQuery({
    queryKey: ["catalog", "search", q.trim()],
    queryFn: ({ signal }) => api.catalog.search(q.trim(), signal),
    enabled: signedIn,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const go = useCallback(
    (to: string) => {
      onClose();
      navigate(to);
    },
    [navigate, onClose],
  );

  const items = useMemo<{ group: string; items: Item[] }[]>(() => {
    const ql = q.trim().toLowerCase();
    const listings: Item[] = (search.data ?? []).slice(0, 8).map((c) => ({
      id: `c:${c.id}`,
      title: c.name,
      small: `${c.kind} · road ${c.road} · ${c.lifecycle}`,
      glyph: c.glyph,
      run: () => go(c.kind === "assistant" && c.access === "open" ? assistantRoute(c.id) : consumerRoute(c)),
    }));
    const commands: Item[] = [
      { id: "g:discover", title: "Discover", small: "the catalog", run: () => go(ROUTES.discover) },
      { id: "g:workspace", title: "My workspace", small: "assistants, requests, usage", run: () => go(ROUTES.workspace) },
      { id: "g:brief", title: "Start or continue a brief", small: "Build · intake", run: () => go(ROUTES.intake) },
      { id: "g:learn", title: "Learn", small: "roads, bootcamp, office hours", run: () => go(ROUTES.learn) },
      { id: "g:settings", title: "Settings", small: "theme, accessibility, notifications", run: () => go(ROUTES.settings) },
      {
        id: "g:signout",
        title: "Sign out",
        run: () => {
          onClose();
          void signOut();
        },
      },
    ].filter((c) => !ql || `${c.title} ${c.small ?? ""}`.toLowerCase().includes(ql));
    const ask: Item[] =
      ql.length > 2
        ? [
            {
              id: "ask",
              title: `Ask the employee assistant: “${q.trim()}”`,
              small: "opens a conversation with your question ready to send",
              glyph: "sparkle",
              run: () => go(assistantRoute("employee-assistant", q.trim())),
            },
          ]
        : [];
    return [
      ...(listings.length ? [{ group: "Assistants, agents, knowledge and tools", items: listings }] : []),
      ...(commands.length ? [{ group: "Go to", items: commands }] : []),
      ...(ask.length ? [{ group: "Or", items: ask }] : []),
    ];
  }, [q, search.data, go, onClose, signOut]);

  const flat = items.flatMap((g) => g.items);
  useEffect(() => {
    setCursor(0);
  }, [q]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, flat.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    }
    if (e.key === "Enter" && flat[cursor]) {
      e.preventDefault();
      track("palette.run", { id: flat[cursor].id });
      flat[cursor].run();
    }
  };

  return (
    <div
      className="palette-scrim"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette hub" role="dialog" aria-modal="true" aria-label="Search and go to" style={{ width: 640 }}>
        <div className="inp">
          <Search size={16} />
          <input
            ref={inputRef}
            className="ctl"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={flat[cursor]?.id}
            placeholder="Search assistants, tools, knowledge… or type a question"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
          />
        </div>
        <div className="list" id="palette-list" role="listbox">
          {items.map((g) => (
            <div key={g.group}>
              <div className="group">{g.group}</div>
              {g.items.map((it) => {
                const i = flat.indexOf(it);
                return (
                  <button
                    key={it.id}
                    id={it.id}
                    type="button"
                    role="option"
                    aria-selected={i === cursor}
                    className="opt"
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => {
                      track("palette.run", { id: it.id });
                      it.run();
                    }}
                  >
                    {it.glyph ? (
                      <span
                        className="ic"
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 7,
                          background: "var(--surface-3)",
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "var(--ink-2)",
                        }}
                      >
                        <Glyph name={it.glyph} size={14} />
                      </span>
                    ) : null}
                    <div className="col" style={{ gap: 0, flex: 1 }}>
                      {it.title}
                      {it.small && <small>{it.small}</small>}
                    </div>
                  </button>
                );
              })}
            </div>
          ))}
          {flat.length === 0 && (
            <div className="muted" style={{ padding: 12, fontSize: 13 }}>
              {search.isPending ? "Searching…" : "Nothing matches."}
            </div>
          )}
        </div>
        <div className="foot">
          <span>
            <span className="kbd">↑↓</span> move
          </span>
          <span>
            <span className="kbd">↵</span> open
          </span>
          <span>
            <span className="kbd">esc</span> close
          </span>
          <span className="sp"></span>
          <span>results are limited to what your role may see</span>
        </div>
      </div>
    </div>
  );
}
