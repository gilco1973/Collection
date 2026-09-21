import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { newId } from "../../api/client";
import { BRIEF_STEPS, type BriefContent, type BriefStepKey } from "../../api/schemas";
import type { Brief } from "../../api/types";
import { useAuth, usePrincipal } from "../../auth/AuthProvider";
import { ROUTES } from "../../routes";
import { ArrowRight, Check, Clock, OkCircle } from "../../ui/icons";
import { Crumbs, HubFoot, HubNav } from "../../ui/HubChrome";
import { PageState } from "../../ui/PageState";
import { useToast } from "../../ui/Toast";
import { useTitle } from "../../ui/useTitle";
import { DataAndToolsStep, ModelStep, OutcomeStep, PeopleStep, ReviewStep, STEP_META, UseCaseStep } from "./steps";
import { useBrief, type SaveState } from "./useBrief";

/**
 * Build → Intake brief. The one page that is the whole intake (spec §7.11
 * step 1): six sections on the left, the section being edited in the middle,
 * and on the right what the platform derives from it as it is written — the
 * road, the cost estimate and what happens next.
 *
 * With no brief id in the route the person's open draft is shown, or an
 * invitation to start one. The default render for the `gk` persona is the
 * published artboard, pixel for pixel.
 */
export default function IntakeBrief() {
  const { briefId } = useParams<{ briefId?: string }>();
  const list = useQuery({ queryKey: ["briefs"], queryFn: ({ signal }) => api.briefs.list(signal), enabled: !briefId });
  const principal = usePrincipal();
  const latestDraft = useMemo(() => {
    const mine = (list.data ?? []).filter((b) => b.createdBy === principal.id && (b.status === "draft" || b.status === "needs_info"));
    return mine.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0]?.id;
  }, [list.data, principal.id]);
  // Once a draft is opened on the id-less route it stays open, so filing it
  // (after which it is no longer "the open draft") does not swap the page.
  const [pinned, setPinned] = useState<string | undefined>();
  useEffect(() => {
    if (!briefId && latestDraft && !pinned) setPinned(latestDraft);
  }, [briefId, latestDraft, pinned]);
  const open = briefId ?? pinned ?? latestDraft;

  if (!briefId && list.isPending) return <PageState kind="loading" text="Loading your briefs…" />;
  if (!briefId && list.error) return <PageState kind="error" text="Your briefs could not be loaded." detail={(list.error as Error).message} />;
  if (!open) return <StartBrief />;
  return <BriefEditor id={open} />;
}

function StartBrief() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { can } = useAuth();
  const key = useRef(newId());
  const create = useMutation({
    mutationFn: () => api.briefs.create(key.current),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["briefs"] });
      navigate(`${ROUTES.intake}/${b.id}`);
    },
    onError: () => {
      key.current = newId();
    },
  });
  return (
    <div className="hub" data-live style={{ minHeight: 700 }}>
      <HubNav active="Build" />
      <div className="hwrap">
        <Crumbs area="Build" page="Intake brief" />
        <div>
          <h1 style={{ fontSize: "24px", fontWeight: "600", letterSpacing: "-.02em" }}>Start an intake brief</h1>
          <div className="muted" style={{ fontSize: "14px", marginTop: "4px" }}>
            A one-page brief is the whole intake. Everything after it is generated from what you file here.
          </div>
        </div>
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="cb" style={{ gap: 12 }}>
            <div className="steps">
              {BRIEF_STEPS.map((k, i) => (
                <div key={k} className="step">
                  <span className="n">{i + 1}</span>
                  <span className="t">
                    {STEP_META[k].title}
                    <small>{STEP_META[k].small}</small>
                  </span>
                </div>
              ))}
            </div>
            {create.error && (
              <div className="banner crit" role="alert">
                <div>The brief could not be started. {(create.error as Error).message}</div>
              </div>
            )}
          </div>
          <div className="cf">
            <Clock className="i muted" />
            <span>about 15 minutes · saved as you go</span>
            <span className="sp"></span>
            {can("brief.create") ? (
              <button type="button" className="btn p" onClick={() => create.mutate()} disabled={create.isPending}>
                Start a brief
                <ArrowRight size={14} />
              </button>
            ) : (
              <span className="muted" data-testid="no-team">
                A brief names the team that owns it. You are in no team yet; ask your lead to add you, then start here.
              </span>
            )}
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}

const SAVE_CHIP: Record<SaveState, { cls: string; text: string }> = {
  saved: { cls: "line", text: "draft saved" },
  dirty: { cls: "line", text: "unsaved changes" },
  saving: { cls: "line busy", text: "saving…" },
  conflict: { cls: "crit", text: "changed elsewhere" },
  error: { cls: "crit", text: "not saved" },
};

/** The value, settled: the first non-null value passes at once, later ones after a pause. */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    if (v == null && value != null) {
      setV(value);
      return;
    }
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms, v]);
  return v;
}

function BriefEditor({ id }: { id: string }) {
  const s = useBrief(id);
  const { can } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const userMoved = useRef(false);

  // Derived cards recompute from the content, a moment after typing stops.
  const debounced = useDebounced(s.content, 500);
  useTitle(s.content?.useCase.name ? `Brief · ${s.content.useCase.name}` : "Intake brief");
  const road = useQuery({
    queryKey: ["brief", id, "road", debounced],
    queryFn: ({ signal }) => api.briefs.road(id, debounced as BriefContent, signal),
    enabled: !!debounced,
    placeholderData: (prev) => prev,
  });
  const estimate = useQuery({
    queryKey: ["brief", id, "estimate", debounced],
    queryFn: ({ signal }) => api.briefs.estimate(id, debounced as BriefContent, signal),
    enabled: !!debounced,
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    if (userMoved.current) headingRef.current?.focus({ preventScroll: false });
  }, [s.step]);

  useEffect(() => {
    if (s.saveState === "conflict") toast.notify("crit", "This draft changed in another tab.", "Reload to see the latest version before editing further.");
    if (s.saveState === "error") toast.notify("warn", "The draft could not be saved.", s.saveDetail ?? "Your changes are kept here; saving will be retried when you continue.");
    // Toast only on transitions into these states.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.saveState]);

  // Warn before leaving with unsaved edits.
  useEffect(() => {
    if (s.saveState !== "dirty" && s.saveState !== "saving") return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [s.saveState]);

  if (s.loading || !s.content || !s.brief) {
    if (s.error)
      return (
        <PageState
          kind="error"
          text="This brief could not be opened."
          detail={(s.error as Error).message}
          action={
            <Link className="btn s" to={ROUTES.workspace}>
              Back to my workspace
            </Link>
          }
        />
      );
    return <PageState kind="loading" text="Opening the brief…" />;
  }

  const brief: Brief = s.brief;
  const content = s.content;
  const editable = brief.status === "draft" || brief.status === "needs_info";
  const needsLead = content.dataAndTools.tierCeiling !== "R";
  const canFile = needsLead ? can("brief.file") : can("brief.file", { ownedByMe: brief.createdBy === s.brief.createdBy });
  const idx = s.stepIndex;
  const nextKey: BriefStepKey | undefined = BRIEF_STEPS[idx + 1];
  const chip = SAVE_CHIP[s.saveState];
  const meta = STEP_META[s.step];
  const loadingSide = road.isPending || estimate.isPending;

  const onContinue = async () => {
    userMoved.current = true;
    if (s.step === "review") {
      const filed = await s.file();
      if (filed) toast.notify("ok", "Brief filed.", `Road ${filed.road ?? "assigned"} · the platform lead confirms within two working days.`);
      return;
    }
    const ok = await s.next();
    if (!ok) toast.notify("warn", "Some fields need attention before continuing.");
  };

  const stepBody = (() => {
    const props = { s, content, errors: s.errors };
    switch (s.step) {
      case "useCase":
        return <UseCaseStep {...props} />;
      case "people":
        return <PeopleStep {...props} />;
      case "dataAndTools":
        return <DataAndToolsStep {...props} />;
      case "model":
        return <ModelStep {...props} />;
      case "outcome":
        return <OutcomeStep {...props} />;
      case "review":
        return <ReviewStep {...props} needsLead={needsLead} canFile={canFile} />;
    }
  })();

  return (
    <div className="hub" data-live data-loading={loadingSide ? "true" : undefined} style={{ minHeight: "1180px" }}>
      <HubNav active="Build" />
      <div className="hwrap">
        <Crumbs area="Build" page="Intake brief" />
        <div>
          <h1 style={{ fontSize: "24px", fontWeight: "600", letterSpacing: "-.02em" }}>{content.useCase.name || "Untitled brief"}</h1>
          <div className="muted" style={{ fontSize: "14px", marginTop: "4px" }}>
            A one-page brief is the whole intake. Everything after it is generated from what you file here.
          </div>
        </div>

        {!editable && (
          <div className="banner ok" role="status">
            <OkCircle size={15} />
            <div>
              <b>Filed{brief.road ? ` · road ${brief.road}` : ""}.</b> The platform lead confirms the road within two working days; registration, namespaces and
              the playground follow. Track it in <Link to={ROUTES.workspace}>my workspace</Link>.
            </div>
          </div>
        )}
        {s.saveState === "conflict" && (
          <div className="banner crit" role="alert">
            <div className="col" style={{ gap: 6, flex: 1 }}>
              <span>
                <b>This draft was saved from another tab.</b> Reload to see the latest version; edits made here since are not saved.
              </span>
              <div className="row">
                <button type="button" className="btn s" onClick={() => void s.reload()}>
                  Reload the draft
                </button>
              </div>
            </div>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "260px minmax(0,1fr) 340px", gap: "20px", minHeight: "0" }}>
          {/* Steps rail */}
          <div className="card " style={{}}>
            <div className="ch">
              <h3>Intake brief</h3>
              <span className="sp"></span>
              <span className={`chip ${editable ? chip.cls : "ok"}`} role="status">
                {editable ? chip.text : brief.status.replace("_", " ")}
              </span>
            </div>
            <div className="cb">
              <nav className="steps" aria-label="Brief sections">
                {BRIEF_STEPS.map((k, i) => {
                  const done = s.completed.includes(k);
                  const on = k === s.step;
                  const cls = `step ${done && !on ? "done" : on ? "on" : ""}`;
                  return (
                    <button
                      key={k}
                      type="button"
                      className={cls}
                      aria-current={on ? "step" : undefined}
                      disabled={!s.canVisit(k)}
                      onClick={() => {
                        userMoved.current = true;
                        s.goTo(k);
                      }}
                    >
                      <span className="n">{done && !on ? <Check size={11} /> : i + 1}</span>
                      <span className="t">
                        {STEP_META[k].title}
                        <small>{STEP_META[k].small}</small>
                      </span>
                    </button>
                  );
                })}
              </nav>
            </div>
            <div className="cf">
              <Clock className="i muted" />
              <span>about 15 minutes</span>
            </div>
          </div>

          {/* Section */}
          <form
            className="card"
            data-guide="intake-form"
            onSubmit={(e) => {
              e.preventDefault();
              void onContinue();
            }}
            aria-busy={s.filing || undefined}
            noValidate
          >
            <div className="ch">
              <div className="col" style={{ gap: "2px" }}>
                <h3 ref={headingRef} tabIndex={-1} style={{ fontSize: "15px" }}>{`${idx + 1} · ${meta.title}`}</h3>
                <span className="muted" style={{ fontSize: "12px" }}>
                  {meta.sub}
                </span>
              </div>
            </div>
            <fieldset
              className="cb"
              style={{ gap: "18px", border: 0, margin: 0, padding: "14px 16px", minWidth: 0 }}
              disabled={!editable || s.saveState === "conflict"}
            >
              {stepBody}
              {s.fileError && (
                <div className="banner crit" role="alert">
                  <div>{s.fileError}</div>
                </div>
              )}
            </fieldset>
            <div className="cf">
              <button
                type="button"
                className="btn g"
                onClick={() => {
                  userMoved.current = true;
                  s.back();
                }}
                disabled={idx === 0}
              >
                Back
              </button>
              <span className="sp"></span>
              {editable && (
                <button
                  type="button"
                  className="btn "
                  onClick={() =>
                    void s
                      .save()
                      .then(() => toast.notify("ok", "Draft saved."))
                      .catch(() => undefined)
                  }
                  disabled={s.saveState === "saving" || s.saveState === "conflict"}
                >
                  Save draft
                </button>
              )}
              {editable && s.step !== "review" && (
                <button type="submit" className="btn p">
                  {`Continue to ${STEP_META[nextKey!].title}`}
                  <ArrowRight size={14} />
                </button>
              )}
              {editable && s.step === "review" && (
                <button type="submit" className="btn p" disabled={!canFile || s.filing || s.saveState === "conflict"}>
                  {s.filing ? "Filing…" : "File the brief"}
                  <ArrowRight size={14} />
                </button>
              )}
              {!editable && (
                <button type="button" className="btn p" onClick={() => navigate(ROUTES.workspace)}>
                  Go to my workspace
                  <ArrowRight size={14} />
                </button>
              )}
            </div>
          </form>

          {/* Derived: road, cost, next */}
          <div className="col" style={{ gap: "16px" }}>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Recommended road</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                {road.data ? (
                  <>
                    <div className="row" style={{ gap: "12px" }}>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: "44px",
                          height: "44px",
                          borderRadius: "10px",
                          background: "var(--accent-soft)",
                          color: "var(--accent-ink)",
                          fontWeight: "700",
                          fontSize: "16px",
                        }}
                      >
                        {road.data.road}
                      </span>
                      <div className="col" style={{ gap: "1px" }}>
                        <b>{road.data.title}</b>
                        <span className="muted" style={{ fontSize: "12px" }}>
                          {road.data.subtitle}
                        </span>
                      </div>
                    </div>
                    <div className={`banner ${road.data.selfService ? "ok" : "accent"}`}>
                      <OkCircle size={15} />
                      <div>
                        <b>{road.data.selfService ? "Self-service." : "Lead confirms."}</b>
                        {` ${road.data.note}`}
                      </div>
                    </div>
                  </>
                ) : (
                  <span className="muted" style={{ fontSize: 12 }}>
                    {road.error ? "The road could not be derived yet." : "Deriving the road from the brief…"}
                  </span>
                )}
              </div>
            </div>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>Estimated cost</h3>
                <span className="sp"></span>
                <span className="chip mono">PLT-DX-4</span>
              </div>
              <div className="cb">
                {estimate.data ? (
                  <div className="kv ">
                    <b>model spend</b>
                    <div className="v">
                      <b>{`≈ $${estimate.data.modelSpendMonthly} a month`}</b> <span className="muted">{estimate.data.modelSpendBasis}</span>
                    </div>
                    <b>review labour</b>
                    <div className="v">{`${estimate.data.reviewHours} hours · ${estimate.data.reviewNote}`}</div>
                    <b>platform share</b>
                    <div className="v">{estimate.data.platformShare}</div>
                    <b>basis</b>
                    <div className="v">{estimate.data.basis}</div>
                  </div>
                ) : (
                  <span className="muted" style={{ fontSize: 12 }}>
                    {estimate.error ? "The estimate is not available right now." : "Estimating…"}
                  </span>
                )}
              </div>
            </div>
            <div className="card " style={{}}>
              <div className="ch">
                <h3>What happens next</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                <div className="steps">
                  {(road.data?.next ?? []).map((n) => (
                    <div key={n.week} className="step">
                      <span className="n">{n.week}</span>
                      <span className="t">
                        {n.title}
                        <small>{n.small}</small>
                      </span>
                    </div>
                  ))}
                  {!road.data && (
                    <span className="muted" style={{ fontSize: 12 }}>
                      Follows the road.
                    </span>
                  )}
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
