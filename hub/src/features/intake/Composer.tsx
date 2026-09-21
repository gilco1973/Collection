import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useFocusTrap } from "../../ui/useFocusTrap";
import { api } from "../../api";
import type { BriefContent } from "../../api/schemas";
import type { DataClass, RegistrySystem, RegistryTool, Tier } from "../../api/types";
import { BASELINE_WHY, baselineFor } from "../../api/baseline";
import { track } from "../../telemetry";
import { Check, Close, Grid, Plus, Search } from "../../ui/icons";
import { TIER_CHIP } from "./steps";
import type { BriefState } from "./useBrief";
import "./composer.css";

/**
 * Compose a new solution from what already exists. The palette on the left is
 * everything the brief may name: the registry's systems of record and their
 * tools, the collection's components, and the bank's own services. The right
 * side is the brief's own section 3, as a drop zone. Dragging (or the Add
 * button, for a keyboard) writes straight into the brief, and the panel shows
 * the consequences as they happen: which system a tool brings with it, the
 * tier ceiling the tools need, the data classes they read, the session limit.
 * Nothing here is a second data model: it edits `content.dataAndTools`.
 */

export type Reuse = { id: string; name: string; kind: string; required?: boolean };
type ItemKind = "system" | "tool" | "component" | "service";
type Item = { kind: ItemKind; id: string; name: string; small: string; tier?: Tier; classes?: DataClass[]; disabled?: string; signed?: boolean };
const MIME = "application/x-hub-item";
const TIER_RANK: Record<Tier, number> = { R: 0, W1: 1, W2: 2, M: 3 };
const CEILING_LABEL: Record<Tier, string> = { R: "Read", W1: "Write with confirmation", W2: "Write with approval", M: "Money" };
const SESSION_CEILING = 15;

export function reusesOf(v: BriefContent["dataAndTools"]): Reuse[] {
  return (v as { reuses?: Reuse[] }).reuses ?? [];
}

export function Composer({ s, content, onClose }: { s: BriefState; content: BriefContent; onClose: () => void }) {
  const v = content.dataAndTools;
  const systems = useQuery({ queryKey: ["registry", "systems"], queryFn: ({ signal }) => api.registry.systems(signal), staleTime: Infinity });
  const tools = useQuery({ queryKey: ["registry", "tools"], queryFn: ({ signal }) => api.registry.tools(signal), staleTime: Infinity });
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: ({ signal }) => api.catalog.get(signal), staleTime: 60_000 });
  const [q, setQ] = useState("");
  const [show, setShow] = useState<"all" | ItemKind>("all");
  const [over, setOver] = useState(false);
  const [last, setLast] = useState<string | undefined>();
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    dialogRef.current?.querySelector<HTMLElement>("input")?.focus();
  }, []);
  useFocusTrap(dialogRef, onClose);

  const reuses = reusesOf(v).filter((r) => !r.required);
  const baseline = baselineFor(content);
  const isBaseline = (id: string) => baseline.some((b) => b.id === id);
  const has = (kind: ItemKind, id: string) =>
    kind === "system"
      ? v.systems.some((x) => x.id === id)
      : kind === "tool"
        ? v.tools.some((x) => x.name === id)
        : reuses.some((x) => x.id === id) || isBaseline(id);

  const items = useMemo<Item[]>(() => {
    const sys = (systems.data ?? []).map<Item>((x) => ({
      kind: "system",
      id: x.id,
      name: x.name,
      small: x.owner,
      disabled: x.contract === "missing" ? "no recorded contract yet; a first consumer cannot name it" : undefined,
    }));
    const byId = new Map((systems.data ?? []).map((x) => [x.id, x]));
    const tl = (tools.data ?? []).map<Item>((t) => ({
      kind: "tool",
      id: t.name,
      name: t.name,
      small: `${t.description} · ${byId.get(t.systemId)?.name ?? t.systemId}`,
      tier: t.tier,
      classes: t.classes,
    }));
    const listings = catalog.data?.listings ?? [];
    const comps = listings
      .filter((l) => l.collection)
      .map<Item>((l) => ({ kind: "component", id: l.id, name: l.name, small: `${l.kind} · road ${l.road} · ${l.description}`, signed: l.lifecycle === "GA" }));
    const svcs = listings
      .filter((l) => !l.collection && l.kind !== "road")
      .map<Item>((l) => ({ kind: "service", id: l.id, name: l.name, small: `${l.kind} · road ${l.road} · ${l.lifecycle}`, signed: l.lifecycle === "GA" }));
    return [...sys, ...tl, ...comps, ...svcs];
  }, [systems.data, tools.data, catalog.data]);

  const shown = items.filter(
    (it) => (show === "all" || it.kind === show) && (!q.trim() || `${it.name} ${it.small}`.toLowerCase().includes(q.trim().toLowerCase())),
  );
  const groups: Array<[ItemKind, string, string]> = [
    ["system", "Systems of record", "from the registry; each needs a recorded contract"],
    ["tool", "Tools", "each carries its tier and the data classes it reads; dropping one brings its system"],
    ["component", "The collection", "reusable components; GA means two named people signed this version"],
    ["service", "The bank's services", "assistants, agents and knowledge services already on the platform"],
  ];

  const add = (kind: ItemKind, id: string) => {
    const it = items.find((x) => x.kind === kind && x.id === id);
    if (!it || it.disabled || has(kind, id)) return;
    if (kind === "system") s.update("dataAndTools", { systems: [...v.systems, { id: it.id, name: it.name }] });
    if (kind === "tool") {
      const t = (tools.data ?? []).find((x) => x.name === id) as RegistryTool;
      const sysRec = (systems.data ?? []).find((x) => x.id === t.systemId) as RegistrySystem | undefined;
      const bringsSystem = sysRec && sysRec.contract === "recorded" && !v.systems.some((x) => x.id === sysRec.id);
      s.update("dataAndTools", {
        tools: [...v.tools, { name: t.name, tier: t.tier, classes: t.classes }],
        ...(bringsSystem ? { systems: [...v.systems, { id: sysRec.id, name: sysRec.name }] } : {}),
      });
      setLast(bringsSystem ? `${t.name} brought ${sysRec.name} with it` : `${t.name} added`);
    }
    if (kind === "component" || kind === "service")
      s.update("dataAndTools", { reuses: [...reuses, { id: it.id, name: it.name, kind }] } as Partial<BriefContent["dataAndTools"]>);
    if (kind !== "tool") setLast(`${it.name} added`);
    track("intake.compose.add", { kind });
  };
  const remove = (kind: ItemKind, id: string) => {
    if (kind === "system") s.update("dataAndTools", { systems: v.systems.filter((x) => x.id !== id) });
    if (kind === "tool") s.update("dataAndTools", { tools: v.tools.filter((x) => x.name !== id) });
    if (kind === "component" || kind === "service")
      s.update("dataAndTools", { reuses: reuses.filter((x) => x.id !== id) } as Partial<BriefContent["dataAndTools"]>);
  };

  const onDragStart = (e: DragEvent, it: Item) => {
    if (it.disabled) {
      e.preventDefault();
      return;
    }
    e.dataTransfer.setData(MIME, JSON.stringify({ kind: it.kind, id: it.id }));
    e.dataTransfer.effectAllowed = "copy";
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    try {
      const { kind, id } = JSON.parse(e.dataTransfer.getData(MIME)) as { kind: ItemKind; id: string };
      add(kind, id);
    } catch {
      /* not one of ours */
    }
  };

  // The consequences of what is composed so far.
  const highest = v.tools.reduce<Tier>((m, t) => (TIER_RANK[t.tier] > TIER_RANK[m] ? t.tier : m), "R");
  const ceilingShort = TIER_RANK[highest] > TIER_RANK[v.tierCeiling];
  const classesNeeded = [...new Set(v.tools.flatMap((t) => t.classes))].filter((c) => !v.dataClasses.includes(c) && c !== "restricted");
  const restrictedTools = v.tools.filter((t) => t.classes.includes("restricted"));
  const overLimit = v.tools.length > SESSION_CEILING;
  const signedReuses = reuses.filter((r) => items.find((i) => i.id === r.id)?.signed).length;

  return (
    <div
      className="palette-scrim"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={dialogRef} className="composer" role="dialog" aria-modal="true" aria-label="Compose from what exists">
        <header className="composer-head">
          <span className="composer-mark" aria-hidden="true">
            <Grid size={16} />
          </span>
          <div className="col" style={{ gap: 1, flex: 1, minWidth: 0 }}>
            <b>Compose from what exists</b>
            <span className="muted" style={{ fontSize: 12.5 }}>
              Drag a system, a tool or a component onto the brief; Add works too. It saves as you go.
            </span>
          </div>
          <button type="button" className="btn p s" onClick={onClose}>
            Done
          </button>
          <button type="button" className="btn g s" aria-label="Close" onClick={onClose}>
            <Close size={14} />
          </button>
        </header>

        <div className="composer-body">
          <section className="composer-palette" aria-label="What exists">
            <div className="composer-tools">
              <label className="composer-search">
                <Search size={14} />
                <input
                  className="ctl"
                  placeholder="Search systems, tools, components…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  aria-label="Search what exists"
                />
              </label>
              <div className="composer-filter" role="tablist" aria-label="Show">
                {(["all", "system", "tool", "component", "service"] as const).map((k) => (
                  <button
                    key={k}
                    type="button"
                    role="tab"
                    aria-selected={show === k}
                    className={`chip line${show === k ? " on" : ""}`}
                    onClick={() => setShow(k)}
                  >
                    {k === "all" ? "All" : k === "system" ? "Systems" : k === "tool" ? "Tools" : k === "component" ? "Collection" : "Services"}
                  </button>
                ))}
              </div>
            </div>
            <div className="composer-list">
              {groups
                .filter(([k]) => show === "all" || show === k)
                .map(([k, title, why]) => {
                  const list = shown.filter((it) => it.kind === k);
                  if (!list.length) return null;
                  return (
                    <div key={k} className="composer-group">
                      <div className="composer-kicker">
                        {title} <span className="muted">· {why}</span>
                      </div>
                      {list.map((it) => {
                        const inBrief = has(it.kind, it.id);
                        return (
                          <div
                            key={`${it.kind}:${it.id}`}
                            className={`composer-item${inBrief ? " in" : ""}${it.disabled ? " off" : ""}`}
                            draggable={!it.disabled && !inBrief}
                            onDragStart={(e) => onDragStart(e, it)}
                            aria-disabled={!!it.disabled || undefined}
                            title={it.disabled ?? (inBrief ? "Already in the brief" : "Drag onto the brief, or press Add")}
                            data-testid={`item-${it.kind}-${it.id}`}
                          >
                            <span className="composer-grip" aria-hidden="true">
                              ⋮⋮
                            </span>
                            {it.tier ? (
                              <span className={`chip ${TIER_CHIP[it.tier]}`}>{it.tier}</span>
                            ) : it.kind === "component" || it.kind === "service" ? (
                              <span className={`chip ${it.signed ? "ok" : "warn"}`}>{it.signed ? "GA" : "preview"}</span>
                            ) : (
                              <span className="chip line">system</span>
                            )}
                            <div className="col" style={{ gap: 0, flex: 1, minWidth: 0 }}>
                              <span className={it.kind === "tool" ? "mono" : ""}>{it.name}</span>
                              <small className="muted">
                                {it.small}
                                {it.classes ? ` · ${it.classes.join(" · ")}` : ""}
                                {it.disabled ? ` · ${it.disabled}` : ""}
                              </small>
                            </div>
                            {inBrief && isBaseline(it.id) ? (
                              <span className="chip accent" title={BASELINE_WHY}>
                                <Check size={11} /> required
                              </span>
                            ) : inBrief ? (
                              <span className="chip ok">
                                <Check size={11} /> in the brief
                              </span>
                            ) : (
                              <button
                                type="button"
                                className="btn g s"
                                disabled={!!it.disabled}
                                onClick={() => add(it.kind, it.id)}
                                aria-label={`Add ${it.name}`}
                              >
                                <Plus size={12} />
                                Add
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              {(systems.isPending || tools.isPending || catalog.isPending) && (
                <span className="muted" style={{ padding: 8, fontSize: 12 }}>
                  Loading what exists…
                </span>
              )}
              {!shown.length && !systems.isPending && !tools.isPending && !catalog.isPending && (
                <span className="muted" style={{ padding: 8, fontSize: 12 }}>
                  Nothing matches. The registry and the catalog only list what your role may see.
                </span>
              )}
            </div>
          </section>

          <section
            className={`composer-brief${over ? " over" : ""}`}
            aria-label="The brief's data and tools"
            data-testid="dropzone"
            onDragOver={(e) => {
              if (e.dataTransfer.types.includes(MIME)) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
                if (!over) setOver(true);
              }
            }}
            onDragLeave={() => setOver(false)}
            onDrop={onDrop}
          >
            <div className="composer-kicker">Your brief · 3 · Data and tools</div>
            <div className="composer-drop-hint" aria-hidden="true">
              {over ? "Drop to add it to the brief" : "Drop anything here"}
            </div>

            <h4>Systems of record</h4>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {v.systems.map((x) => (
                <button
                  key={x.id}
                  type="button"
                  className="chip accent"
                  onClick={() => remove("system", x.id)}
                  aria-label={`${x.name} · remove`}
                  title="Remove"
                >
                  <Check size={12} /> {x.name} <Close size={10} />
                </button>
              ))}
              {!v.systems.length && <span className="muted composer-empty">None yet. A tool brings its system with it.</span>}
            </div>

            <h4>
              Tools <span className={`muted${overLimit ? " crit" : ""}`}>{`${v.tools.length} of ${SESSION_CEILING}`}</span>
            </h4>
            <div className="composer-rows">
              {v.tools.map((t) => (
                <div key={t.name} className="composer-row">
                  <span className={`chip ${TIER_CHIP[t.tier]}`}>{t.tier}</span>
                  <span className="mono" style={{ flex: 1, minWidth: 0 }}>
                    {t.name}
                  </span>
                  <small className="muted">{t.classes.join(" · ")}</small>
                  <button type="button" className="bare" aria-label={`Remove ${t.name}`} onClick={() => remove("tool", t.name)}>
                    <Close size={13} />
                  </button>
                </div>
              ))}
              {!v.tools.length && (
                <span className="muted composer-empty">None yet. Every tool has a tier; the highest one sets the ceiling the brief needs.</span>
              )}
            </div>

            {baseline.length > 0 && (
              <>
                <h4>
                  Required with any tool <span className="muted">the harness</span>
                </h4>
                <div className="composer-rows" data-testid="baseline">
                  {baseline.map((b) => (
                    <div key={b.id} className="composer-row locked" title={b.why}>
                      <span className="chip accent">required</span>
                      <div className="col" style={{ gap: 0, flex: 1, minWidth: 0 }}>
                        <span>{b.name}</span>
                        <small className="muted">{b.why}</small>
                      </div>
                      <span className="composer-lock" role="img" aria-label="required, cannot be removed">
                        🔒
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            <h4>Reused from what exists</h4>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {reuses.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="chip line"
                  onClick={() => remove(r.kind as ItemKind, r.id)}
                  aria-label={`${r.name} · remove`}
                  title="Remove"
                >
                  {r.name} <Close size={10} />
                </button>
              ))}
              {!reuses.length && <span className="muted composer-empty">None yet. A signed component here is review time saved.</span>}
            </div>

            <div className="composer-consequences" aria-live="polite">
              <div className="composer-kicker">What this means</div>
              <ul>
                <li>
                  Highest tier so far: <span className={`chip ${TIER_CHIP[highest]}`}>{highest}</span>
                  {highest === "M" ? (
                    <>
                      {" "}
                      · <b className="crit">a money tool is refused for a first consumer</b>; remove it or propose it to an approver instead.
                    </>
                  ) : ceilingShort ? (
                    <>
                      {" "}
                      · the ceiling is <b>{CEILING_LABEL[v.tierCeiling]}</b>, which does not cover it.{" "}
                      <button type="button" className="btn s" onClick={() => s.update("dataAndTools", { tierCeiling: highest })}>
                        Set the ceiling to {CEILING_LABEL[highest]}
                      </button>
                    </>
                  ) : (
                    <>
                      {" "}
                      · the ceiling <b>{CEILING_LABEL[v.tierCeiling]}</b> covers it.
                    </>
                  )}
                </li>
                <li>
                  {classesNeeded.length ? (
                    <>
                      The tools read <b>{classesNeeded.join(" · ")}</b>, not yet ticked under data classes.{" "}
                      <button
                        type="button"
                        className="btn s"
                        onClick={() => s.update("dataAndTools", { dataClasses: [...new Set([...v.dataClasses, ...classesNeeded])] })}
                      >
                        Tick {classesNeeded.join(" and ")}
                      </button>
                    </>
                  ) : (
                    <>Data classes ticked cover every tool.</>
                  )}
                </li>
                {restrictedTools.length > 0 && (
                  <li>
                    <b className="crit">
                      {restrictedTools.map((t) => t.name).join(" · ")} {restrictedTools.length === 1 ? "reads" : "read"} restricted data, which a first consumer cannot use
                    </b>
                    ; remove {restrictedTools.length === 1 ? "it" : "them"} or take the use case to the platform team for a data-class exception.
                  </li>
                )}
                <li>
                  {overLimit ? (
                    <b className="crit">Over the 15-tool session ceiling: remove tools or split the consumer.</b>
                  ) : (
                    <>{`${SESSION_CEILING - v.tools.length} tools left under the session ceiling.`}</>
                  )}
                </li>
                {baseline.length > 0 && <li>{BASELINE_WHY} They are written into the brief when it is filed and cannot be removed.</li>}
                <li>
                  {highest === "R"
                    ? "Reads only: a read profile registers itself; the lead confirms only the road."
                    : "A write profile: your team lead files the brief, and the road carries confirmation or dual control."}
                </li>
                {reuses.length > 0 && (
                  <li>{`${signedReuses} of ${reuses.length} reused ${reuses.length === 1 ? "item is" : "items are"} signed at their current version; the rest are previews.`}</li>
                )}
                {last && <li className="muted">{last}.</li>}
              </ul>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
