import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useCancelAudit } from "../api/hooks";
import type { AuditDetailData } from "../api/types";
import { formatDate } from "../format";
import { ModeBadge, StatusBadge } from "./Badges";
import { ErrorBox, btn, btnDanger } from "./States";

interface Props { audit: AuditDetailData; operator: boolean; forced?: boolean }

export default function AuditHeader({ audit: a, operator, forced }: Props) {
  const { t, i18n } = useTranslation();
  const cancel = useCancelAudit(a.audit_id);
  const [confirming, setConfirming] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const wasConfirming = useRef(false);
  const s = a.summary;
  const running = a.status === "in_progress";
  useEffect(() => {
    if (confirming) confirmButton.current?.focus();
    else if (wasConfirming.current) (trigger.current?.disabled ? heading.current : trigger.current)?.focus({ preventScroll: true });
    wasConfirming.current = confirming;
  }, [confirming]);
  const close = () => setConfirming(false);
  return (
    <div className="flex flex-col gap-4">
      <div className={`motion-safe:animate-rise-slow flex flex-col gap-3 rounded-l border bg-surface px-6 py-5 shadow-1 ${a.dry_run ? "border-rule" : "border-warn"}`}>
        <div className="flex flex-wrap items-center gap-2">
          <ModeBadge dryRun={a.dry_run} large />
          <StatusBadge status={a.status} />
          <span className="text-[12px] text-muted">{t(`audits.types.${a.audit_type}`)}</span>
          <span className="ms-auto flex flex-wrap gap-2">
            {running && operator && (
              <button ref={trigger} type="button" onClick={() => setConfirming(true)} aria-expanded={confirming}
                disabled={confirming || cancel.isPending || cancel.isSuccess} className={`${btn} border-crit text-crit`}>
                {cancel.isSuccess ? t("audit.cancelling") : t("audit.cancel")}
              </button>
            )}
            <a href={api.exportUrl(a.audit_id, "md")} className={btn}>{t("audit.export")}</a>
            <a href={api.exportUrl(a.audit_id, "json")} className={btn}>{t("audit.exportJson")}</a>
          </span>
        </div>
        <h1 ref={heading} tabIndex={-1} dir="ltr" className="break-all font-mono text-[22px] font-semibold tracking-[-0.01em] outline-none">{a.audit_id}</h1>
        {confirming && (
          <div role="group" aria-label={t("audit.cancel")} onKeyDown={(e) => { if (e.key === "Escape") close(); }}
            className="motion-safe:animate-rise flex flex-wrap items-center gap-2 rounded border border-crit/30 bg-crit-soft p-3 text-[13px] text-crit">
            <span>{t("audit.cancelPrompt")}</span>
            <button ref={confirmButton} type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(undefined, { onSettled: close })} className={btnDanger}>{t("audit.confirmCancel")}</button>
            <button type="button" onClick={close} className={btn}>{t("audit.keepRunning")}</button>
          </div>
        )}
        {cancel.error && <ErrorBox error={cancel.error} />}
        {forced && <p role="status" className="rounded-s bg-warn-soft px-3 py-2 text-[13px] text-warn">{t("run.forcedDry")}</p>}
        <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
          <b className="text-[12px] font-medium text-muted">{t("audits.date")}</b><span>{formatDate(s.audit_date, i18n.language)}{s.completed_at && <> · {t("audit.completedAt")} {formatDate(s.completed_at, i18n.language)}</>}</span>
          {a.requested_by && <><b className="text-[12px] font-medium text-muted">{t("audit.requestedBy")}</b><bdi>{a.requested_by}</bdi></>}
          {a.reason && <><b className="text-[12px] font-medium text-muted">{t("audit.reason")}</b><span>{a.reason}</span></>}
          {a.capabilities.length > 0 && <><b className="text-[12px] font-medium text-muted">{t("audit.capabilities")}</b><bdi className="font-mono text-[12px]">{a.capabilities.join(", ")}</bdi></>}
        </div>
        {a.error && <p role="alert" className="rounded-s bg-crit-soft p-2 text-[13px] text-crit">{t("audit.error")}: {a.error}</p>}
      </div>
    </div>
  );
}
