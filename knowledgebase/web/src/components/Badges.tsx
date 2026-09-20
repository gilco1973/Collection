import { useTranslation } from "react-i18next";
import type { AuditStatus, Severity } from "../api/types";

/** Hub chip: 20px tall, 11px semibold, soft ground, no border. */
export const chip = "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-[5px] px-[7px] text-[11px] font-semibold tracking-[0.01em]";

const severityClass: Record<Severity, string> = {
  critical: "bg-crit-soft text-crit",
  error: "bg-w2-soft text-w2",
  warning: "bg-warn-soft text-warn",
  info: "bg-accent-soft text-accent-ink",
};

const statusClass: Record<string, string> = {
  in_progress: "bg-accent-soft text-accent-ink",
  completed: "bg-ok-soft text-ok",
  failed: "bg-crit-soft text-crit",
  cancelled: "bg-r-soft text-r",
  draft: "bg-r-soft text-r",
  active: "bg-ok-soft text-ok",
  deprecated: "bg-warn-soft text-warn",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { t } = useTranslation();
  return (
    <span className={`${chip} ${severityClass[severity]}`}>
      <span aria-hidden="true">{{ critical: "●", error: "▲", warning: "◆", info: "○" }[severity]}</span>
      {t(`severity.${severity}`)}
    </span>
  );
}

export function StatusBadge({ status }: { status: AuditStatus | string | null }) {
  const { t } = useTranslation();
  const key = status && statusClass[status] ? status : "unknown";
  return <span className={`${chip} ${statusClass[key] ?? statusClass.draft}`}>{t(`status.${key}`)}</span>;
}

export function ModeBadge({ dryRun, large = false }: { dryRun: boolean; large?: boolean }) {
  const { t } = useTranslation();
  const size = large ? "h-6 px-2.5 text-[12px]" : "h-5 px-[7px] text-[11px]";
  return dryRun ? (
    <span title={t("mode.dryHelp")} className={`inline-flex items-center gap-1 rounded-[5px] border border-dashed border-rule-2 bg-surface font-mono font-medium text-ink-2 ${size}`}>
      <span aria-hidden="true">⚗</span>
      {t("mode.dry")}
    </span>
  ) : (
    <span title={t("mode.liveHelp")} className={`inline-flex items-center gap-1 rounded-[5px] bg-warn font-mono font-semibold text-on-warn ${size}`}>
      <span aria-hidden="true">⚡</span>
      {t("mode.live")}
    </span>
  );
}
