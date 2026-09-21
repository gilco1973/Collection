import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { type BriefContent, type BriefStepKey, type FieldErrors } from "../../api/schemas";
import type { DataClass, RegistrySystem, Tier } from "../../api/types";
import { usePrincipal } from "../../auth/AuthProvider";
import { CheckRow, Field, NumberInput, RadioCard, Seg, TextInput } from "../../ui/fields";
import { Check, Close, Grid } from "../../ui/icons";
import type { BriefState } from "./useBrief";
import { Composer, reusesOf } from "./Composer";
import { baselineFor } from "../../api/baseline";

/** Titles and the one-line summaries the steps rail and the section headers show (§7.11). */
export const STEP_META: Record<BriefStepKey, { title: string; small: string; sub: string }> = {
  useCase: { title: "Use case", small: "name, problem, channel", sub: "what the consumer is for, in the words of the people who will use it" },
  people: { title: "People", small: "owner, expert, allowance", sub: "who owns it, who labels the cases, and how much of their week that takes" },
  dataAndTools: {
    title: "Data and tools",
    small: "systems, tools, classes, tier",
    sub: "what the consumer reads, what it may do, and the most it may ever do",
  },
  model: { title: "Model", small: "need and ceiling", sub: "how much model the work needs, and the highest class of data it may see" },
  outcome: { title: "Outcome", small: "metric, baseline, target", sub: "one number the consumer is meant to move, measured today and at each phase exit" },
  review: { title: "Review and file", small: "road, cost, what happens next", sub: "check the brief, confirm the road, and file it" },
};

export const TIER_CHIP: Record<Tier, string> = { R: "", W1: "warn", W2: "w2", M: "crit" };

const CHANNELS = [
  { value: "operator" as const, label: "Operator" },
  { value: "customer" as const, label: "Customer" },
  { value: "partner" as const, label: "Partner" },
  { value: "batch" as const, label: "Batch" },
];

type StepProps = { s: BriefState; content: BriefContent; errors: FieldErrors };

/* ---------- 1 · Use case ---------- */
export function UseCaseStep({ s, content, errors }: StepProps) {
  const p = usePrincipal();
  const v = content.useCase;
  return (
    <>
      <Field label="Name" id="uc-name" error={errors["useCase.name"]} help="one line, in the words of the desk that will use it">
        <TextInput
          id="uc-name"
          value={v.name}
          onChange={(name) => s.update("useCase", { name })}
          placeholder="Payments returns triage for the collections desk"
          maxLength={80}
        />
      </Field>
      <Field label="The problem today" id="uc-problem" error={errors["useCase.problem"]} help="what happens now, by hand, and roughly how long it takes">
        <TextInput
          id="uc-problem"
          multiline
          value={v.problem}
          onChange={(problem) => s.update("useCase", { problem })}
          placeholder="Each morning the desk reads the returns out of COS one by one…"
        />
      </Field>
      <Field label="Channel" error={errors["useCase.channel"]} help="who talks to the consumer; customer and partner channels open on road R3 in Phase 5">
        <Seg label="Channel" value={v.channel} options={CHANNELS} onChange={(channel) => s.update("useCase", { channel })} />
      </Field>
      <Field
        label="Team"
        id="uc-team"
        error={p.teams.length === 0 ? ["You are in no team yet. Ask your lead to add you; a brief needs the team that owns it."] : errors["useCase.teamId"]}
        help="the team that owns the consumer and its cost centre"
      >
        <div className="inp">
          <select id="uc-team" className="ctl" value={v.teamId} onChange={(e) => s.update("useCase", { teamId: e.target.value })}>
            <option value="">Choose a team…</option>
            {p.teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
                {t.lead ? " · you lead" : ""}
              </option>
            ))}
            {!p.teams.some((t) => t.id === v.teamId) && v.teamId && <option value={v.teamId}>{v.teamId}</option>}
          </select>
        </div>
      </Field>
    </>
  );
}

/* ---------- 2 · People ---------- */
export function PeopleStep({ s, content, errors }: StepProps) {
  const v = content.people;
  return (
    <>
      <Field label="Business owner" id="pp-bo" error={errors["people.businessOwner"]} help="accountable for the outcome; signs the monthly review from step 7">
        <TextInput
          id="pp-bo"
          value={v.businessOwner}
          onChange={(businessOwner) => s.update("people", { businessOwner })}
          placeholder="D. Ruiz, Payments operations"
        />
      </Field>
      <Field label="Product owner" id="pp-po" error={errors["people.productOwner"]} help="runs the build and the sandbox with the embedded engineer">
        <TextInput id="pp-po" value={v.productOwner} onChange={(productOwner) => s.update("people", { productOwner })} />
      </Field>
      <Field
        label="Domain expert"
        id="pp-de"
        error={errors["people.domainExpert"]}
        help="labels the evaluation cases (PLT-ONB-11); named here so the allowance is real"
      >
        <TextInput id="pp-de" value={v.domainExpert} onChange={(domainExpert) => s.update("people", { domainExpert })} placeholder="S. Okafor" />
      </Field>
      <Field
        label="Labelling allowance"
        id="pp-hours"
        error={errors["people.labellingHoursPerWeek"]}
        help="hours a week the expert gives through sandbox; under one hour stalls the corpus gate"
      >
        <NumberInput
          id="pp-hours"
          value={v.labellingHoursPerWeek || ""}
          min={0}
          max={40}
          step={1}
          suffix="hours a week"
          onChange={(n) => s.update("people", { labellingHoursPerWeek: n === "" ? 0 : n })}
        />
      </Field>
    </>
  );
}

/* ---------- 3 · Data and tools ---------- */
export function DataAndToolsStep({ s, content, errors }: StepProps) {
  const v = content.dataAndTools;
  const systems = useQuery({ queryKey: ["registry", "systems"], queryFn: ({ signal }) => api.registry.systems(signal), staleTime: Infinity });
  const [pick, setPick] = useState<"system" | "tool" | null>(null);
  const popRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pick || pick === "tool") return; // the composer is a dialog and closes itself
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !popRef.current?.contains(e.target as Node)) setPick(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [pick]);

  const setClass = (c: DataClass, on: boolean) =>
    s.update("dataAndTools", { dataClasses: on ? [...new Set([...v.dataClasses, c])] : v.dataClasses.filter((x) => x !== c) });
  const addSystem = (sys: RegistrySystem) => {
    s.update("dataAndTools", { systems: [...v.systems, { id: sys.id, name: sys.name }] });
    setPick(null);
  };
  const removeSystem = (id: string) => s.update("dataAndTools", { systems: v.systems.filter((x) => x.id !== id) });
  const removeTool = (name: string) => s.update("dataAndTools", { tools: v.tools.filter((x) => x.name !== name) });

  return (
    <>
      <Field label="Channel">
        <Seg label="Channel" value={content.useCase.channel} options={CHANNELS} onChange={(channel) => s.update("useCase", { channel })} />
      </Field>
      <Field label="Systems of record" error={errors["dataAndTools.systems"]} help="each system must have a recorded contract in the registry">
        <div className="row" style={{ flexWrap: "wrap", position: "relative" }}>
          {v.systems.map((sys) => (
            <button
              key={sys.id}
              type="button"
              className="chip accent"
              title="Remove this system"
              aria-label={`${sys.name} · remove`}
              onClick={() => removeSystem(sys.id)}
            >
              <Check size={12} />
              {sys.name}
            </button>
          ))}
          <button
            type="button"
            className="chip line"
            aria-haspopup="listbox"
            aria-expanded={pick === "system"}
            onClick={() => setPick(pick === "system" ? null : "system")}
          >
            + add a system
          </button>
          {pick === "system" && (
            <div ref={popRef} className="pop" role="listbox" aria-label="Systems of record">
              {(systems.data ?? [])
                .filter((x) => !v.systems.some((y) => y.id === x.id))
                .map((x) => (
                  <button
                    key={x.id}
                    type="button"
                    role="option"
                    aria-selected={false}
                    className="opt"
                    aria-disabled={x.contract === "missing"}
                    onClick={() => x.contract === "recorded" && addSystem(x)}
                  >
                    <div className="col" style={{ gap: 0 }}>
                      {x.name}
                      <small>
                        {x.owner}
                        {x.contract === "missing" ? " · no recorded contract yet" : ""}
                      </small>
                    </div>
                  </button>
                ))}
              {systems.isPending && (
                <span className="muted" style={{ padding: 8, fontSize: 12 }}>
                  Loading the registry…
                </span>
              )}
            </div>
          )}
        </div>
      </Field>
      <Field label="Tools needed" error={errors["dataAndTools.tools"]}>
        <table className="t ">
          <thead>
            <tr>
              <th className="">Tool</th>
              <th className="">Tier</th>
              <th className="">Data classes</th>
              <th className=""></th>
            </tr>
          </thead>
          <tbody>
            {v.tools.map((t) => (
              <tr key={t.name} className="">
                <td className="">
                  <span className="mono">{t.name}</span>
                </td>
                <td className="">
                  <span className={`chip ${TIER_CHIP[t.tier]}`}>{t.tier}</span>
                </td>
                <td className="">{t.classes.join(" · ")}</td>
                <td className="">
                  <button type="button" className="bare" aria-label={`Remove ${t.name}`} onClick={() => removeTool(t.name)}>
                    <Close size={14} className="i muted" />
                  </button>
                </td>
              </tr>
            ))}
            {v.tools.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No tools yet. Browse the catalog to add the first one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: "8px", position: "relative" }}>
          <button
            type="button"
            className="btn s"
            aria-haspopup="dialog"
            aria-expanded={pick === "tool"}
            onClick={() => setPick(pick === "tool" ? null : "tool")}
          >
            <Grid size={14} />
            Browse the catalog
          </button>
          <span
            className="muted"
            style={{ fontSize: "12px" }}
          >{`${v.tools.length} tools · ${v.tools.length > 15 ? "over" : "under"} the 15-tool session ceiling`}</span>
          {pick === "tool" && <Composer s={s} content={content} onClose={() => setPick(null)} />}
        </div>
      </Field>
      {reusesOf(v).some((r) => !r.required) && (
        <Field
          label="Reused from what exists"
          help="components of the collection and services of the bank the consumer builds on; a signed one is review time saved"
        >
          <div className="row" style={{ flexWrap: "wrap" }}>
            {reusesOf(v)
              .filter((r) => !r.required)
              .map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="chip line"
                  title="Remove"
                  aria-label={`${r.name} · remove`}
                  onClick={() => s.update("dataAndTools", { reuses: reusesOf(v).filter((x) => x.id !== r.id) })}
                >
                  {r.name}
                  <Close size={10} />
                </button>
              ))}
          </div>
        </Field>
      )}
      <Field label="Data classes read" error={errors["dataAndTools.dataClasses"]}>
        <CheckRow label="internal" note="no extra review" checked={v.dataClasses.includes("internal")} onChange={(on) => setClass("internal", on)} />
        <CheckRow
          label="confidential"
          note="Privacy reviews the delta · 5 business days"
          checked={v.dataClasses.includes("confidential")}
          onChange={(on) => setClass("confidential", on)}
        />
        <CheckRow
          label="restricted"
          note="not available to a first consumer"
          checked={v.dataClasses.includes("restricted")}
          onChange={(on) => setClass("restricted", on)}
        />
      </Field>
      <Field label="Tier ceiling" error={errors["dataAndTools.tierCeiling"]} help="the most the consumer may ever do; raising it later re-enters review">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", minHeight: "0" }}>
          <RadioCard
            name="ceiling"
            value="R"
            checked={v.tierCeiling === "R"}
            onChange={() => s.update("dataAndTools", { tierCeiling: "R" })}
            title="Read"
            sub="profile read · self-service"
          />
          <RadioCard
            name="ceiling"
            value="W1"
            checked={v.tierCeiling === "W1"}
            onChange={() => s.update("dataAndTools", { tierCeiling: "W1" })}
            title="Write with confirmation"
            sub="W1 · lead confirms the brief"
          />
          <RadioCard
            name="ceiling"
            value="W2"
            checked={v.tierCeiling === "W2"}
            onChange={() => s.update("dataAndTools", { tierCeiling: "W2" })}
            title="Write with approval"
            sub="W2 · dual control · lead confirms"
          />
        </div>
      </Field>
    </>
  );
}

/* ---------- 4 · Model ---------- */
export function ModelStep({ s, content, errors }: StepProps) {
  const v = content.model;
  const highest: DataClass = content.dataAndTools.dataClasses.includes("restricted")
    ? "restricted"
    : content.dataAndTools.dataClasses.includes("confidential")
      ? "confidential"
      : "internal";
  return (
    <>
      <Field label="Model need" error={errors["model.need"]} help="the platform picks the model inside the class; a consumer names a need, not a vendor (PD3)">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", minHeight: "0" }}>
          <RadioCard
            name="need"
            value="none"
            checked={v.need === "none"}
            onChange={() => s.update("model", { need: "none" })}
            title="No generative model"
            sub="classical rules or retrieval only"
          />
          <RadioCard
            name="need"
            value="utility"
            checked={v.need === "utility"}
            onChange={() => s.update("model", { need: "utility" })}
            title="Utility"
            sub="classification, extraction, short answers"
          />
          <RadioCard
            name="need"
            value="workhorse"
            checked={v.need === "workhorse"}
            onChange={() => s.update("model", { need: "workhorse" })}
            title="Workhorse"
            sub="reasoning over tools and documents · default"
          />
          <RadioCard
            name="need"
            value="frontier"
            checked={v.need === "frontier"}
            onChange={() => s.update("model", { need: "frontier" })}
            title="Frontier"
            sub="hardest cases · justified by the outcome metric"
          />
        </div>
      </Field>
      <Field
        label="Classification ceiling for the model"
        error={errors["model.classificationCeiling"]}
        help={`the highest class of data the model may see; the brief reads ${highest}, so the ceiling cannot be lower`}
      >
        <Seg
          label="Classification ceiling"
          value={v.classificationCeiling}
          onChange={(classificationCeiling) => s.update("model", { classificationCeiling })}
          options={[
            { value: "internal", label: "Internal" },
            { value: "confidential", label: "Confidential" },
            { value: "restricted", label: "Restricted" },
          ]}
        />
      </Field>
      <Field label="Substitution" help="allow the platform to substitute an equivalent model inside the class during an incident (PLT-MDL-9)">
        <CheckRow
          label="the platform may substitute the model"
          note="recommended · no change to the consumer's contract"
          checked={v.substitute}
          onChange={(substitute) => s.update("model", { substitute })}
        />
      </Field>
    </>
  );
}

/* ---------- 5 · Outcome ---------- */
export function OutcomeStep({ s, content, errors }: StepProps) {
  const v = content.outcome;
  return (
    <>
      <Field
        label="Outcome metric"
        id="oc-metric"
        error={errors["outcome.metric"]}
        help="one number the consumer is meant to move (PLT-ONB-10); it is re-measured at every phase exit"
      >
        <TextInput id="oc-metric" value={v.metric} onChange={(metric) => s.update("outcome", { metric })} placeholder="minutes per case" />
      </Field>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", minHeight: "0" }}>
        <Field label="Unit" id="oc-unit" error={errors["outcome.unit"]}>
          <TextInput id="oc-unit" value={v.unit} onChange={(unit) => s.update("outcome", { unit })} placeholder="minutes" />
        </Field>
        <Field label="Baseline today" id="oc-baseline" error={errors["outcome.baseline"]}>
          <NumberInput
            id="oc-baseline"
            value={Number.isFinite(v.baseline) ? v.baseline : ""}
            onChange={(n) => s.update("outcome", { baseline: n === "" ? Number.NaN : n })}
          />
        </Field>
        <Field label="Target" id="oc-target" error={errors["outcome.target"]}>
          <NumberInput
            id="oc-target"
            value={Number.isFinite(v.target) ? v.target : ""}
            onChange={(n) => s.update("outcome", { target: n === "" ? Number.NaN : n })}
          />
        </Field>
      </div>
      <Field
        label="Baseline measured on"
        id="oc-date"
        error={errors["outcome.measuredOn"]}
        help="the date the baseline was taken; older than a quarter and the platform lead asks for a fresh one"
      >
        <div style={{ width: 220 }}>
          <TextInput id="oc-date" type="date" value={v.measuredOn} onChange={(measuredOn) => s.update("outcome", { measuredOn })} />
        </div>
      </Field>
    </>
  );
}

/* ---------- 6 · Review and file ---------- */
export function ReviewStep({ s, content, errors, needsLead, canFile }: StepProps & { needsLead: boolean; canFile: boolean }) {
  const c = content;
  const sec = (title: string, step: BriefStepKey, rows: Array<[string, string]>) => (
    <div className="col" style={{ gap: 6 }}>
      <div className="row">
        <b style={{ fontSize: 13 }}>{title}</b>
        <span className="sp"></span>
        <button type="button" className="btn g s" onClick={() => s.goTo(step)}>
          Edit
        </button>
      </div>
      <div className="kv">
        {rows.map(([k, val]) => (
          <FragmentRow key={k} k={k} v={val} />
        ))}
      </div>
      {Object.entries(errors)
        .filter(([k]) => k.startsWith(`${step}.`))
        .map(([k, msgs]) => (
          <span key={k} className="err" style={{ fontSize: 11.5, color: "var(--crit)" }}>
            {msgs[0]}
          </span>
        ))}
    </div>
  );
  return (
    <>
      {sec("1 · Use case", "useCase", [
        ["name", c.useCase.name || "—"],
        ["problem", c.useCase.problem || "—"],
        ["channel", c.useCase.channel],
        ["team", c.useCase.teamId || "—"],
      ])}
      {sec("2 · People", "people", [
        ["business owner", c.people.businessOwner || "—"],
        ["product owner", c.people.productOwner || "—"],
        ["domain expert", c.people.domainExpert || "—"],
        ["labelling", `${c.people.labellingHoursPerWeek || 0} hours a week`],
      ])}
      {sec("3 · Data and tools", "dataAndTools", [
        ["systems", c.dataAndTools.systems.map((x) => x.name).join(" · ") || "—"],
        ["tools", c.dataAndTools.tools.map((t) => `${t.name} (${t.tier})`).join(", ") || "—"],
        ...(baselineFor(c).length
          ? [
              [
                "harness",
                `${baselineFor(c)
                  .map((b) => b.name)
                  .join(" · ")} · required with any tool`,
              ] as [string, string],
            ]
          : []),
        ...(reusesOf(c.dataAndTools).some((r) => !r.required)
          ? [
              [
                "reuses",
                reusesOf(c.dataAndTools)
                  .filter((r) => !r.required)
                  .map((r) => r.name)
                  .join(" · "),
              ] as [string, string],
            ]
          : []),
        ["data classes", c.dataAndTools.dataClasses.join(" · ") || "—"],
        ["tier ceiling", c.dataAndTools.tierCeiling],
      ])}
      {sec("4 · Model", "model", [
        ["need", c.model.need],
        ["classification ceiling", c.model.classificationCeiling],
        ["substitution", c.model.substitute ? "allowed" : "not allowed"],
      ])}
      {sec("5 · Outcome", "outcome", [
        ["metric", c.outcome.metric || "—"],
        ["baseline", Number.isFinite(c.outcome.baseline) ? `${c.outcome.baseline} ${c.outcome.unit}` : "—"],
        ["target", Number.isFinite(c.outcome.target) ? `${c.outcome.target} ${c.outcome.unit}` : "—"],
        ["measured on", c.outcome.measuredOn || "—"],
      ])}
      {needsLead && !canFile && (
        <div className="banner warn" role="status">
          <div>
            <b>Your team lead files this brief.</b> A write profile ({c.dataAndTools.tierCeiling}) needs the lead's confirmation. Your draft is saved; ask your
            lead to open it from the team workspace and file it.
          </div>
        </div>
      )}
      {needsLead && canFile && (
        <div className="banner accent" role="status">
          <div>
            <b>Lead confirmation.</b> Filing a write profile ({c.dataAndTools.tierCeiling}) as the team lead is the confirmation the platform records. The
            second line reviews the delta before staging.
          </div>
        </div>
      )}
      <Field label="Confirmation" error={errors["review.acknowledged"]}>
        <CheckRow
          label="I have read what happens next and the estimated cost"
          checked={c.review.acknowledged === true}
          onChange={(acknowledged) => s.update("review", { acknowledged: acknowledged as true })}
        />
      </Field>
    </>
  );
}

function FragmentRow({ k, v }: { k: string; v: string }) {
  return (
    <>
      <b>{k}</b>
      <div className="v">{v}</div>
    </>
  );
}
