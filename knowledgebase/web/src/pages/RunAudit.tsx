import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useContract, useMe, useStartAudit } from "../api/hooks";
import { ModeBadge } from "../components/Badges";
import ConfirmWithReason from "../components/ConfirmWithReason";
import { Card, ErrorBox, Loading, btnPrimary, input as inputClass } from "../components/States";
import { usePageTitle } from "../usePageTitle";

const input = `${inputClass} mt-1`;
const needsAtlassian = (capability: string) => capability.toLowerCase().includes("atlassian");

export default function RunAudit() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const contract = useContract();
  const start = useStartAudit();
  const budgetHelp = useId();
  const liveHelp = useId();
  usePageTitle(t("run.title"));
  const [type, setType] = useState<"agent" | "offline">("agent");
  const [live, setLive] = useState(false);
  const [caps, setCaps] = useState<string[] | null>(null);
  const [maxTurns, setMaxTurns] = useState("");
  const [budget, setBudget] = useState("");
  const [network, setNetwork] = useState(false);
  const [confirming, setConfirming] = useState(false);
  if (me.isPending || contract.isPending) return <Loading />;
  if (me.error) return <ErrorBox error={me.error} onRetry={() => me.refetch()} />;
  if (contract.error) return <ErrorBox error={contract.error} onRetry={() => contract.refetch()} />;
  const operator = me.data?.role === "operator";
  const liveAllowed = me.data?.live_allowed ?? false;
  const atlassian = me.data?.atlassian_configured ?? false;
  const available = contract.data.capabilities.filter((c) => atlassian || !needsAtlassian(c));
  const selected = caps ?? available;
  const submit = (reason?: string) => {
    start.mutate(
      {
        type, dry_run: !live, capabilities: type === "agent" ? selected : undefined,
        max_turns: maxTurns ? Number(maxTurns) : undefined, max_budget_usd: budget ? Number(budget) : undefined, network, reason,
      },
      { onSuccess: (r) => navigate(`/audits/${r.audit_id}?tab=summary`, { state: { forced: r.forced_dry_run } }) },
    );
  };
  const startLabel = live ? t("run.startLive") : t("run.startDry");
  const noCapability = type === "agent" && selected.length === 0;
  const ceiling = contract.data.defaults.max_budget_usd;
  if (!operator) {
    // Running the librarian is an operator concern: readers get the explanation, not the (disabled) form.
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{t("run.title")}</h1>
        <p role="alert" className="rounded-s bg-warn-soft px-3 py-2 text-[13px] text-warn">{t("run.operatorOnly")} <Link to="/settings" className="underline">{t("nav.settings")}</Link></p>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{t("run.title")}</h1>
      <Card className="motion-safe:animate-rise-slow">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (live) setConfirming(true); else submit(); }}>
          <fieldset className="space-y-1.5 text-[13px]">
            <legend className="mb-1 text-[12px] font-medium text-muted">{t("run.type")}</legend>
            <label className="block"><input type="radio" name="type" className="me-2" checked={type === "agent"} onChange={() => setType("agent")} />{t("run.typeAgent")}</label>
            <label className="block"><input type="radio" name="type" className="me-2" checked={type === "offline"} onChange={() => setType("offline")} />{t("run.typeOffline")}</label>
          </fieldset>
          <fieldset className="space-y-1.5 text-[13px]">
            <legend className="mb-1 text-[12px] font-medium text-muted">{t("audits.mode")}</legend>
            <label className="flex items-center gap-2"><input type="radio" name="mode" checked={!live} onChange={() => setLive(false)} /><ModeBadge dryRun /> <span className="text-muted">{t("mode.dryHelp")}</span></label>
            <label className="flex items-center gap-2"><input type="radio" name="mode" disabled={!liveAllowed} checked={live} onChange={() => setLive(true)} /><ModeBadge dryRun={false} /> <span id={liveHelp} className="text-muted">{liveAllowed ? t("mode.liveHelp") : t("run.liveLocked")}</span></label>
          </fieldset>
          {type === "agent" && (
            <>
              <fieldset className="text-sm">
                <legend className="mb-1 text-[12px] font-medium text-muted">{t("run.capabilities")}</legend>
                <div className="flex flex-wrap gap-3">
                  {contract.data.capabilities.map((c) => {
                    const locked = !atlassian && needsAtlassian(c);
                    return (
                      <label key={c}>
                        <input type="checkbox" className="me-1" disabled={locked} checked={selected.includes(c)}
                          onChange={(e) => setCaps(e.target.checked ? [...selected, c] : selected.filter((x) => x !== c))} />
                        {c}{locked && <span className="ms-1 text-xs">({t("run.atlassianLocked")})</span>}
                      </label>
                    );
                  })}
                </div>
                {noCapability && <p role="alert" className="mt-1 text-xs text-warn">{t("run.needCapability")}</p>}
              </fieldset>
              <div className="grid gap-3 text-sm sm:grid-cols-2">
                <label>{t("run.maxTurns")}<input type="number" min={1} max={200} placeholder={String(contract.data.defaults.max_turns)} value={maxTurns} onChange={(e) => setMaxTurns(e.target.value)} className={input} /></label>
                <div>
                  <label>{t("run.budget")}<input type="number" min={0.05} step={0.05} max={ceiling} placeholder={String(ceiling)} value={budget} onChange={(e) => setBudget(e.target.value)} aria-describedby={budgetHelp} className={input} /></label>
                  <p id={budgetHelp} className="text-xs text-muted">{t("run.budgetHelp", { max: ceiling })}</p>
                </div>
              </div>
            </>
          )}
          <label className="block text-sm"><input type="checkbox" className="me-2" checked={network} onChange={(e) => setNetwork(e.target.checked)} />{t("run.network")}</label>
          {start.error && <ErrorBox error={start.error} />}
          <button type="submit" disabled={!operator || start.isPending || noCapability} aria-describedby={live ? liveHelp : undefined} className={live ? `${btnPrimary} border-warn bg-warn hover:border-warn hover:bg-warn text-on-warn` : btnPrimary}>{startLabel}</button>
        </form>
      </Card>
      {confirming && (
        <ConfirmWithReason title={t("run.liveRun")} description={t("run.liveConfirm")} token="LIVE" confirmLabel={t("run.startLive")} busy={start.isPending}
          onConfirm={(reason) => { setConfirming(false); submit(reason); }} onCancel={() => setConfirming(false)} />
      )}
    </div>
  );
}
