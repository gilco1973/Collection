import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import type { ConsumerKind, ConsumerSummary } from "../../api/types";
import { usePrincipal } from "../../auth/AuthProvider";
import { primaryRole } from "../../auth/permits";
import { assistantRoute, consumerRoute, ROUTES } from "../../routes";
import { Seg } from "../../ui/fields";
import { HubFoot, HubNav } from "../../ui/HubChrome";
import { ArrowRight, Plus, Search } from "../../ui/icons";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useTitle } from "../../ui/useTitle";
import { ListingCard } from "./ListingCard";

type Tab = "all" | "assistants" | "agents" | "knowledge" | "tools" | "roads";
const TABS: Array<{ key: Tab; label: string; kind?: ConsumerKind }> = [
  { key: "all", label: "All" },
  { key: "assistants", label: "Assistants", kind: "assistant" },
  { key: "agents", label: "Agents", kind: "agent" },
  { key: "knowledge", label: "Knowledge", kind: "knowledge" },
  { key: "tools", label: "Tools and APIs", kind: "tool" },
  { key: "roads", label: "Roads and templates", kind: "road" },
];

/** Discover: what this person may use today, the catalog, and the way in for a new use case. */
export default function Discover() {
  const p = usePrincipal();
  const navigate = useNavigate();
  const palette = usePalette();
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: ({ signal }) => api.catalog.get(signal) });
  const requests = useQuery({ queryKey: ["requests"], queryFn: ({ signal }) => api.requests.list(signal) });
  const [tab, setTab] = useState<Tab>("all");
  const [view, setView] = useState<"cards" | "list">("cards");
  useTitle("Discover");

  const cat = catalog.data;
  const availableIds = useMemo(() => new Set((cat?.available ?? []).map((c) => c.id)), [cat]);
  const shown = useMemo<ConsumerSummary[]>(() => {
    if (!cat) return [];
    const kind = TABS.find((t) => t.key === tab)?.kind;
    if (kind) return cat.listings.filter((l) => l.kind === kind);
    // "All" is the rest of the catalog: what is not already in "Available to you", roads aside (they have their own tab).
    return cat.listings.filter((l) => !availableIds.has(l.id) && l.kind !== "road" && !l.collection);
  }, [cat, tab, availableIds]);
  const pendingFor = useMemo(() => new Set((requests.data ?? []).filter((r) => r.status === "pending").map((r) => r.consumerId)), [requests.data]);

  if (catalog.isPending) return <PageState kind="loading" text="Loading the catalog…" />;
  if (catalog.error || !cat) return <PageState kind="error" text="The catalog could not be loaded." detail={(catalog.error as Error)?.message} />;

  return (
    <div className="hub" data-live style={{ minHeight: "1660px" }}>
      <HubNav active="Discover" onSearch={palette.open} />
      <div className="hwrap">
        <div className="hero">
          <div className="row">
            <span className="chip line">{`${p.name} · ${primaryRole(p)} · ${p.teams[0]?.id ?? "no team"}`}</span>
            <span className="chip accent">{`${cat.availableCount} services available to you`}</span>
          </div>
          <h1>What do you want to do with AI today?</h1>
          <p className="lede">
            Every assistant, agent and knowledge service here runs on the platform, so your identity, the bank’s policy, a budget and an audit trail come with
            it. Nothing here is a side door.
          </p>
          <button type="button" className="bigsearch" onClick={palette.open} aria-label="Search, or ask the assistant (⌘K)">
            <Search size={16} />
            <span>Summarise this case, draft the R10 letter, find the late-file procedure…</span>
            <span className="sp"></span>
            <span className="kbd">⌘K</span>
          </button>
          <div className="sugg">
            {cat.suggestions.map((s) => (
              <button key={s} type="button" onClick={() => navigate(assistantRoute("employee-assistant", s))}>
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="hsec">
          <div className="hh">
            <h2>Available to you</h2>
            <span className="sub">by your role and channel · request what you cannot see</span>
            <span className="sp"></span>
          </div>
          <div className="cards">
            {cat.available.map((c) => (
              <ListingCard key={c.id} c={c} requested={pendingFor.has(c.id)} />
            ))}
          </div>
        </div>

        <div className="hsec">
          <div className="hh">
            <h2>Browse the catalog</h2>
            <span className="sub">{`${cat.counts.all} listings · every one registered, evaluated and audited`}</span>
            <span className="sp"></span>
            <Seg
              label="Catalog view"
              value={view}
              options={[
                { value: "cards", label: "Cards" },
                { value: "list", label: "List" },
              ]}
              onChange={setView}
            />
          </div>
          <div className="tabs" role="tablist" data-guide="discover-tabs">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                className={`tab${tab === t.key ? " on" : ""}`}
                onClick={() => setTab(t.key)}
              >
                {t.key === "all" ? (
                  <>
                    All <span className="chip">{cat.counts.all}</span>
                  </>
                ) : (
                  t.label
                )}
              </button>
            ))}
          </div>
          {view === "cards" ? (
            <div className="cards">
              {shown.map((c) => (
                <ListingCard key={c.id} c={c} requested={pendingFor.has(c.id)} />
              ))}
              {tab === "all" && (
                <div className="lc" style={{ borderStyle: "dashed", background: "transparent", boxShadow: "none" }}>
                  <div className="row">
                    <span className="ic">
                      <Plus size={18} />
                    </span>
                  </div>
                  <h3>Bring your own use case</h3>
                  <p>
                    File a one-page brief. A read-profile consumer on an open road registers itself; the lead confirms only the road, within two working days.
                  </p>
                  <div className="foot" style={{ borderTop: "0" }}>
                    <span>six weeks to production</span>
                    <span className="sp"></span>
                    <Link className="btn ink s" to={ROUTES.intake}>
                      Start a brief
                      <ArrowRight size={14} />
                    </Link>
                  </div>
                </div>
              )}
              {shown.length === 0 && tab !== "all" && (
                <div className="muted" style={{ fontSize: 13, padding: 8 }}>
                  Nothing in this part of the catalog is visible to your role yet.
                </div>
              )}
            </div>
          ) : (
            <table className="t ">
              <thead>
                <tr>
                  <th>Listing</th>
                  <th>Kind</th>
                  <th>Road</th>
                  <th>Lifecycle</th>
                  <th>Access</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link to={consumerRoute(c)} style={{ color: "inherit", fontWeight: 500 }}>
                        {c.name}
                      </Link>
                      <div className="muted" style={{ fontSize: 12, whiteSpace: "normal" }}>
                        {c.description}
                      </div>
                    </td>
                    <td>{c.kind}</td>
                    <td>
                      <span className="chip line">{c.road}</span>
                    </td>
                    <td>
                      <span className={`chip ${c.lifecycle === "GA" ? "ok" : c.lifecycle === "preview" ? "warn" : "crit"}`}>{c.lifecycle}</span>
                    </td>
                    <td className="muted">
                      {c.access === "open" ? "open to you" : c.access === "request" ? c.footNote : c.access === "contract" ? "contract only" : "view only"}
                    </td>
                    <td>
                      <Link className="btn s" to={c.kind === "assistant" && c.access === "open" ? assistantRoute(c.id) : consumerRoute(c)}>
                        {c.access === "open" ? "Open" : "View"}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="band">
          <div className="col" style={{ gap: "10px" }}>
            <h2>Building something for your team?</h2>
            <p>
              Pick a road, generate the repository, get an embedded platform engineer for two weeks and a two-day bootcamp. Security, Privacy and Model Risk
              review only the delta from the road’s baseline.
            </p>
            <div className="row">
              <Link className="btn " to={ROUTES.intake}>
                Start an intake brief
                <ArrowRight size={14} />
              </Link>
              <Link className="btn g" to={`${ROUTES.learn}#roads`}>
                See the six roads
              </Link>
            </div>
          </div>
          <div className="facts">
            <div>
              <b>6 weeks</b>
              <span>intake to production, read profile</span>
            </div>
            <div>
              <b>2 weeks</b>
              <span>to sandbox with an embedded engineer</span>
            </div>
            <div>
              <b>15 min</b>
              <span>runnable example for every capability</span>
            </div>
          </div>
        </div>

        <div className="card " style={{}}>
          <div className="ch">
            <h3>What changed this week</h3>
            <span className="sp"></span>
            <Link className="btn g s" to={`${ROUTES.learn}#updates`}>
              All updates
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="cb">
            {cat.changes.map((r) => (
              <div key={r.text} className="row" style={{ fontSize: "13px" }}>
                <span className="mono muted" style={{ width: "52px" }}>
                  {r.date}
                </span>
                <span className={`chip ${r.kind.kind ?? ""}`}>{r.kind.text}</span>
                <span>{r.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}
