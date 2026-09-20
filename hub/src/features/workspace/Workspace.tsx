import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { newId } from "../../api/client";
import type { TeamConsumer, Workspace as WorkspaceData } from "../../api/types";
import { assistantRoute, ROUTES } from "../../routes";
import { track } from "../../telemetry";
import { HubFoot, HubNav } from "../../ui/HubChrome";
import { Glyph, InfoCircle, Plus } from "../../ui/icons";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useToast } from "../../ui/Toast";
import { useTitle } from "../../ui/useTitle";

const STAGES = ["Intake", "Register", "Build", "Sandbox", "Review", "Staging", "Operate"];
const GLYPH_FOR: Record<string, "sparkle" | "pulse" | "book"> = {
  "employee-assistant": "sparkle",
  "investigation-triage": "pulse",
  "policy-and-procedures": "book",
};

/** My workspace: what this person uses, what their team is building, their requests, usage and playground. */
export default function Workspace() {
  const navigate = useNavigate();
  const palette = usePalette();
  const toast = useToast();
  const qc = useQueryClient();
  const ws = useQuery({ queryKey: ["workspace"], queryFn: ({ signal }) => api.workspace.get(signal) });
  const rotate = useMutation({
    mutationFn: () => api.workspace.rotatePlaygroundKey(newId()),
    onSuccess: (r) => {
      track("playground.key_rotated");
      qc.setQueryData<WorkspaceData>(["workspace"], (w) => (w ? { ...w, playground: { ...w.playground, keyMasked: r.keyMasked } } : w));
      toast.notify("ok", "Playground key rotated.", "The previous key stops working in 10 minutes.");
    },
    onError: () => toast.notify("crit", "The key could not be rotated."),
  });
  useTitle("My workspace");

  if (ws.isPending) return <PageState kind="loading" text="Loading your workspace…" />;
  if (ws.error || !ws.data) return <PageState kind="error" text="Your workspace could not be loaded." detail={(ws.error as Error)?.message} />;
  const w = ws.data;

  const consumerTo = (c: TeamConsumer) => (c.briefId ? `${ROUTES.intake}/${c.briefId}` : `/discover/agents/${c.id.replace(/^agent:/, "")}`);

  return (
    <div className="hub" data-live style={{ minHeight: "1120px" }}>
      <HubNav active="My workspace" onSearch={palette.open} />
      <div className="hwrap">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "600", letterSpacing: "-.02em" }}>My workspace</h1>
            <div
              className="muted"
              style={{ fontSize: "14px", marginTop: "4px" }}
            >{`${w.header.name} · ${w.header.role} · ${w.header.team} · cost centre ${w.header.costCentre}`}</div>
          </div>
          <span className="sp"></span>
          <Link className="btn ink" to={ROUTES.intake}>
            <Plus size={14} />
            Start a brief
          </Link>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 400px", gap: "24px", minHeight: "0" }}>
          <div className="col" style={{ gap: "16px", minWidth: "0" }}>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Your assistants</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                {w.assistants.map((a) => (
                  <div key={a.consumerId} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--rule)" }}>
                    <span className={`av ${a.ai ? "ai" : ""}`}>
                      <Glyph name={GLYPH_FOR[a.consumerId] ?? "sparkle"} size={13} />
                    </span>
                    <div className="col" style={{ gap: "1px", flex: "1" }}>
                      <b>{a.name}</b>
                      <span className="muted" style={{ fontSize: "12px" }}>
                        {a.sub}
                      </span>
                    </div>
                    <span className={`chip ${a.lifecycle === "GA" ? "ok" : "warn"}`}>{a.lifecycle}</span>
                    <button type="button" className="btn s" onClick={() => navigate(assistantRoute(a.consumerId))}>
                      Open
                    </button>
                  </div>
                ))}
                {w.assistants.length === 0 && (
                  <span className="muted" style={{ fontSize: 13 }}>
                    Nothing yet. Open an assistant from Discover and it appears here.
                  </span>
                )}
              </div>
            </div>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Your team’s consumers</h3>
                <span className="sp"></span>
                <span className="chip ink">{w.teamConsumers.length}</span>
              </div>
              <div className="cb">
                {w.teamConsumers.map((c) => (
                  <div key={c.id} className="col" style={{ padding: "12px 0", borderBottom: "1px solid var(--rule)", gap: "8px" }}>
                    <div className="row">
                      <Link to={consumerTo(c)} className="mono" style={{ fontWeight: "500", color: "inherit" }}>
                        {c.name}
                      </Link>
                      <span className={`chip ${c.status.kind ?? ""}`}>{c.status.text}</span>
                      <span className="sp"></span>
                      <span className="muted" style={{ fontSize: "12px" }}>
                        {c.stepNote}
                      </span>
                    </div>
                    <div className="pipe" role="img" aria-label={`step ${c.step} of 7`}>
                      {c.pipe.map((s, i) => (
                        <span key={i} className={`s ${s}`}></span>
                      ))}
                    </div>
                    <div className="row" style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                      {STAGES.map((s, i) => (
                        <StageLabel key={s} label={s} last={i === STAGES.length - 1} />
                      ))}
                      <span className="sp"></span>
                      <span>{c.note}</span>
                    </div>
                  </div>
                ))}
                {w.teamConsumers.length === 0 && (
                  <span className="muted" style={{ fontSize: 13 }}>
                    Your team has nothing on the platform yet. A brief is the way in.
                  </span>
                )}
              </div>
              <div className="cf">
                <span>stages follow §7.11 of the platform specification; a failed gate returns to Build, never to Intake</span>
              </div>
            </div>
          </div>
          <div className="col" style={{ gap: "16px" }}>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Your requests</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                {w.requests.map((r) => (
                  <div key={r.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--rule)" }}>
                    <div className="col" style={{ gap: "1px", flex: "1" }}>
                      <b>{r.title}</b>
                      <span className="muted" style={{ fontSize: "12px" }}>
                        {r.note}
                      </span>
                    </div>
                    <span className={`chip ${r.status === "pending" ? "warn" : r.status === "granted" ? "ok" : "crit"}`}>{r.status}</span>
                  </div>
                ))}
                {w.requests.length === 0 && (
                  <span className="muted" style={{ fontSize: 13 }}>
                    No requests. Ask for access or a higher ladder from a listing.
                  </span>
                )}
              </div>
            </div>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Usage and budget</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                <div className="kv ">
                  <b>sandbox this month</b>
                  <div className="v">
                    <b>{w.usage.sandboxMonth}</b> <span className="muted">{w.usage.sandboxNote}</span>
                  </div>
                  <b>production</b>
                  <div className="v">
                    <span className="muted">{w.usage.productionNote}</span>
                  </div>
                  <b>playground today</b>
                  <div className="v">
                    {`${w.usage.playgroundToday} of ${w.usage.playgroundBudget}`}
                    <div className="meter" role="progressbar" aria-valuenow={w.usage.playgroundPct} aria-valuemin={0} aria-valuemax={100}>
                      <i
                        className={w.usage.playgroundPct >= 90 ? "c" : w.usage.playgroundPct >= 70 ? "w" : ""}
                        style={{ width: `${w.usage.playgroundPct}%` }}
                      ></i>
                    </div>
                  </div>
                </div>
                <div className="banner" style={{ marginTop: "6px" }}>
                  <InfoCircle size={15} />
                  <div>Every playground call is attributed and budgeted like any other, so experiments are observable and never a second path.</div>
                </div>
              </div>
            </div>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Playground</h3>
                <span className="sp"></span>
                <span className="chip line">per-developer budget</span>
              </div>
              <div className="cb">
                <div className="kv ">
                  <b>gateway</b>
                  <div className="v">
                    <span className="mono">{w.playground.gateway}</span>
                  </div>
                  <b>key</b>
                  <div className="v">
                    <span className="mono">{w.playground.keyMasked}</span>{" "}
                    <button type="button" className="link" onClick={() => rotate.mutate()} disabled={rotate.isPending}>
                      rotate
                    </button>
                  </div>
                  <b>fixtures</b>
                  <div className="v">{w.playground.fixtures}</div>
                  <b>example</b>
                  <div className="v">
                    <Link to={`${ROUTES.learn}#example`}>{w.playground.example}</Link>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}

function StageLabel({ label, last }: { label: string; last: boolean }) {
  return (
    <>
      <span>{label}</span>
      {!last && <span>·</span>}
    </>
  );
}
