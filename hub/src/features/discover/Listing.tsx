import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { NotFoundError } from "../../api/errors";
import type { ConsumerDetail } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { assistantRoute, ROUTES } from "../../routes";
import { HubFoot, HubNav } from "../../ui/HubChrome";
import { ArrowRight, Db, Doc, Glyph, OkCircle, Play, Pulse, Shield } from "../../ui/icons";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useTitle } from "../../ui/useTitle";
import { NotFound } from "../../screens/Status";
import { useCreateRequest } from "../requests/useCreateRequest";

const TIER_CHIP: Record<string, string> = { R: "", W1: "warn", W2: "w2", M: "money", R5: "line" };
const EVIDENCE_ICON = { doc: Doc, db: Db, shield: Shield, pulse: Pulse };

/** A listing: what a consumer does, may read and do, its evidence, cost, and how to start. */
export default function Listing() {
  const { slug = "" } = useParams<{ kind: string; slug: string }>();
  const navigate = useNavigate();
  const palette = usePalette();
  const { can, principal } = useAuth();
  const q = useQuery({ queryKey: ["consumer", slug], queryFn: ({ signal }) => api.consumers.get(slug, signal), enabled: !!slug });
  const requests = useQuery({ queryKey: ["requests"], queryFn: ({ signal }) => api.requests.list(signal) });
  const create = useCreateRequest();
  useTitle(q.data?.name);

  if (q.isPending) return <PageState kind="loading" text="Opening the listing…" />;
  if (q.error instanceof NotFoundError) return <NotFound />;
  if (q.error || !q.data) return <PageState kind="error" text="The listing could not be loaded." detail={(q.error as Error)?.message} />;
  const d: ConsumerDetail = q.data;

  const ladderPending = (requests.data ?? []).some((r) => r.kind === "ladder" && r.consumerId === d.id && r.status === "pending");
  const accessPending = (requests.data ?? []).some((r) => r.kind !== "ladder" && r.consumerId === d.id && r.status === "pending");
  const canAskLadder = d.access === "open" && d.youActAt !== d.ladderMax && can("consumer.request_ladder", { consumerId: d.id, ladder: d.ladderMax });
  const openTo = d.kind === "assistant" ? assistantRoute(d.id) : assistantRoute(d.id);
  const iconBg =
    d.icon === "w"
      ? "var(--warn-soft)"
      : d.icon === "a"
        ? "var(--accent-soft)"
        : d.icon === "m"
          ? "var(--model-soft)"
          : d.icon === "p"
            ? "var(--money-soft)"
            : "var(--surface-3)";
  const iconFg =
    d.icon === "w" ? "var(--warn)" : d.icon === "a" ? "var(--accent-ink)" : d.icon === "m" ? "var(--model)" : d.icon === "p" ? "var(--money)" : "var(--ink-2)";
  const crumbKindTo = `/discover`;

  return (
    <div className="hub" data-live style={{ minHeight: "1400px" }}>
      <HubNav active="Discover" onSearch={palette.open} />
      <div className="hwrap">
        <div className="row muted" style={{ fontSize: "13px" }}>
          <Link to={ROUTES.discover} style={{ color: "inherit" }}>
            {d.crumbs[0]}
          </Link>
          <span>/</span>
          <Link to={crumbKindTo} style={{ color: "inherit" }}>
            {d.crumbs[1]}
          </Link>
          <span>/</span>
          <b style={{ color: "var(--ink)" }}>{d.crumbs[2] ?? d.name}</b>
        </div>
        <div className="hero" style={{ padding: "28px 32px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 380px", gap: "32px", alignItems: "start" }}>
            <div className="col" style={{ gap: "12px" }}>
              <div className="row" style={{ gap: "14px" }}>
                <span
                  className={`ic ${d.icon}`}
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "12px",
                    background: iconBg,
                    color: iconFg,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Glyph name={d.glyph} size={22} />
                </span>
                <div>
                  <h1 style={{ fontSize: "26px" }}>{d.name}</h1>
                  <div className="muted" style={{ fontSize: "13.5px" }}>
                    {d.description}
                  </div>
                </div>
              </div>
              <div className="row" style={{ flexWrap: "wrap" }}>
                {d.headerChips.map((c) => (
                  <span key={c.text} className={`chip ${c.kind ?? ""}`}>
                    {c.text}
                  </span>
                ))}
              </div>
              <div className="row" style={{ marginTop: "4px" }}>
                {d.access === "open" && (
                  <button type="button" className="btn p" onClick={() => navigate(openTo)}>
                    Open in the portal
                    <ArrowRight size={14} />
                  </button>
                )}
                {d.access === "open" && (
                  <button type="button" className="btn " onClick={() => navigate(`${openTo}?playground=1`)}>
                    <Play size={14} />
                    Try in playground
                  </button>
                )}
                {d.access === "request" && can("consumer.request_access", { consumerId: d.id }) && (
                  <button
                    type="button"
                    className={`btn p${accessPending ? " dis" : ""}`}
                    disabled={accessPending || create.isPending}
                    onClick={() => create.mutate({ kind: d.requestKind ?? "access", consumerId: d.id })}
                  >
                    {accessPending ? "Access requested" : "Request access"}
                  </button>
                )}
                {canAskLadder && (
                  <button
                    type="button"
                    className={`btn g${ladderPending ? " dis" : ""}`}
                    disabled={ladderPending || create.isPending}
                    onClick={() => create.mutate({ kind: "ladder", consumerId: d.id, ladder: d.ladderMax })}
                  >
                    {ladderPending ? `Ladder ${d.ladderMax} requested` : `Request ladder ${d.ladderMax}`}
                  </button>
                )}
                {d.access === "view" && (
                  <span className="muted" style={{ fontSize: 12.5 }}>
                    view only for your role · owner {d.footNote.replace(/^owner /, "")}
                  </span>
                )}
                {d.access === "contract" && (
                  <span className="muted" style={{ fontSize: 12.5 }}>
                    {d.footNote}
                  </span>
                )}
              </div>
            </div>
            {d.tiles.length > 0 && (
              <div className="tiles" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
                {d.tiles.map((t) => (
                  <div key={t.label} className="tile">
                    <div className="l">{t.label}</div>
                    <div className="v">
                      {t.value}
                      {t.small && <small>{t.small}</small>}
                    </div>
                    <div className="d">{t.note}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 380px", gap: "24px", minHeight: "0" }}>
          <div className="col" style={{ gap: "16px", minWidth: "0" }}>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>What it does</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                {d.does.map((line) => (
                  <div key={line} className="row" style={{ gap: "10px", alignItems: "flex-start", fontSize: "13.5px" }}>
                    <span style={{ color: "var(--ok)", marginTop: "2px" }}>
                      <OkCircle />
                    </span>
                    <span>{line}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>What it can read and do</h3>
                <span className="sp"></span>
                <span className="chip mono">{`catalog ${d.catalog.name}${d.catalog.signed ? " · signed" : ""}`}</span>
              </div>
              <div className="cb">
                <table className="t ">
                  <thead>
                    <tr>
                      <th className="">Operation</th>
                      <th className="">Tier</th>
                      <th className="">Data classes</th>
                      <th className="">What you see</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.catalog.entries.map((e) => (
                      <tr key={e.op} className="">
                        <td className="">
                          <span className="mono">{e.op}</span>
                        </td>
                        <td className="">
                          <span className={`chip ${TIER_CHIP[e.tier] ?? ""}`}>{e.tier}</span>
                        </td>
                        <td className="">{e.classes}</td>
                        <td className="">{e.note}</td>
                      </tr>
                    ))}
                    {d.catalog.entries.length === 0 && (
                      <tr>
                        <td colSpan={4} className="muted">
                          No operations are recorded for this listing.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            {(d.trust.length > 0 || d.evidence.length > 0) && (
              <div className="card " style={{}}>
                <div className="ch">
                  <h3>Trust and evidence</h3>
                  <span className="sp"></span>
                </div>
                <div className="cb">
                  <div className="tiles">
                    {d.trust.map((t) => (
                      <div key={t.label} className="tile">
                        <div className="l">{t.label}</div>
                        <div className="v">
                          {t.value}
                          {t.small && <small>{t.small}</small>}
                        </div>
                        <div className="d">{t.note}</div>
                      </div>
                    ))}
                  </div>
                  <div className="row" style={{ marginTop: "12px", gap: "14px", fontSize: "13px" }}>
                    {d.evidence.map((e) => {
                      const I = EVIDENCE_ICON[e.icon];
                      return (
                        <span key={e.label} style={{ display: "contents" }}>
                          <I className="i muted" />
                          <a href={e.href} target="_blank" rel="noreferrer">
                            {e.label}
                          </a>
                        </span>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
            {d.cost.length > 0 && (
              <div className="card " style={{}}>
                <div className="ch">
                  <h3>Cost and usage</h3>
                  <span className="sp"></span>
                </div>
                <div className="cb">
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "24px", minHeight: "0" }}>
                    {d.cost.map((c) => (
                      <div key={c.label} className="col" style={{ gap: "2px" }}>
                        <span className="muted" style={{ fontSize: "12px" }}>
                          {c.label}
                        </span>
                        <b style={{ fontSize: "16px" }}>{c.value}</b>
                        <span className="muted" style={{ fontSize: "12px" }}>
                          {c.note}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="col" style={{ gap: "16px" }}>
            {d.getStarted.length > 0 && (
              <div className="card " style={{}}>
                <div className="ch">
                  <h3>Get started</h3>
                  <span className="sp"></span>
                </div>
                <div className="cb">
                  <div className="steps">
                    {d.getStarted.map((s) => (
                      <div key={s.n} className={`step ${s.state}`}>
                        <span className="n">{s.n}</span>
                        <span className="t">
                          {s.title}
                          <small>{s.small}</small>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {d.owner.length > 0 && (
              <div className="card " style={{}}>
                <div className="ch">
                  <h3>Owner and support</h3>
                  <span className="sp"></span>
                </div>
                <div className="cb">
                  <div className="kv ">
                    {d.owner.map((o) => (
                      <Kv key={o.label} k={o.label} v={o.value} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            {d.versions.length > 0 && (
              <div className="card " style={{}}>
                <div className="ch">
                  <h3>Versions</h3>
                  <span className="sp"></span>
                  <a className="btn g s" href={d.changelogHref} target="_blank" rel="noreferrer">
                    Changelog
                  </a>
                </div>
                <div className="cb">
                  {d.versions.map((v) => (
                    <div key={v.version} className="row" style={{ fontSize: "12.5px" }}>
                      <span className="mono">{v.version}</span>
                      <span className={`chip ${v.state === "current" ? "ok" : v.state === "supported" ? "line" : "crit"}`}>{v.state}</span>
                      <span className="sp"></span>
                      <span className="muted">{v.date}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {principal && d.youActAt !== d.ladderMax && d.access === "open" && !canAskLadder && (
              <div className="banner">
                <div>
                  You act at ladder {d.youActAt} here; ladder {d.ladderMax} needs your lead to raise your own ceiling first.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <>
      <b>{k}</b>
      <div className="v">{v}</div>
    </>
  );
}
