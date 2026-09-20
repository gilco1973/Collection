import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Finding, LibrarianAction } from "../api/types";
import { formatDate } from "../format";
import { SeverityBadge } from "./Badges";
import { Empty } from "./States";

export function FindingsList({ findings }: { findings: Finding[] }) {
  const { t } = useTranslation();
  if (!findings.length) return <Empty text={t("audit.noFindings")} />;
  return (
    <ul className="divide-y divide-rule">
      {findings.map((f, n) => (
        <li key={`${f.check}-${f.path}-${f.line ?? 0}-${n}`} className="flex flex-col gap-1 py-2 md:flex-row md:items-start md:gap-3">
          <SeverityBadge severity={f.severity} />
          <div className="min-w-0 flex-1">
            <Link to={`/kb/page/${f.path}`} dir="ltr" className="break-all font-mono text-sm text-accent underline">{f.path}</Link>
            {f.line != null && <span className="ms-2 text-xs text-muted">{t("audit.line", { line: f.line })}</span>}
            <p className="text-sm">
              <span className="me-2 rounded bg-surface-3 px-1 font-mono text-xs">{f.check}</span>
              {f.message}
            </p>
            {f.fix_hint && <p className="text-xs text-muted">{f.fix_hint}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ActionsList({ actions, auditId, canRollback }: { actions: LibrarianAction[]; auditId: string; canRollback: boolean }) {
  const { t, i18n } = useTranslation();
  if (!actions.length) return <Empty text={t("audit.noActions")} />;
  return (
    <ul className="divide-y divide-rule">
      {actions.map((a) => {
        const state = a.dry_run ? t("audit.proposed") : a.rolled_back ? t("audit.rolledBack") : t("audit.applied");
        const tone = a.dry_run ? "border border-dashed border-rule-2" : a.rolled_back ? "bg-surface-3" : "bg-ok-soft";
        return (
          <li key={a.action_id} className="flex flex-col gap-1 py-2 md:flex-row md:items-start md:gap-3">
            <span className={`rounded px-2 py-0.5 text-xs ${tone}`}>{state}</span>
            <div className="min-w-0 flex-1 text-sm">
              <span className="me-2 font-mono text-xs">{a.action_type}</span>
              <span dir="ltr" className="break-all font-mono">{a.path}</span>
              <span className="ms-2 text-xs text-muted">{formatDate(a.timestamp, i18n.language)}</span>
              <p className="text-xs text-muted">{a.description}</p>
              {a.rolled_back && (
                <p className="text-xs text-muted">
                  {t("audit.rolledBackDetail", { reason: a.rollback_reason ?? t("common.notAvailable"), when: formatDate(a.rollback_timestamp, i18n.language) })}
                  {a.rollback_forced && <span className="ms-1 rounded bg-warn-soft px-1 text-warn">{t("audit.rolledBackForced")}</span>}
                </p>
              )}
            </div>
            {canRollback && !a.dry_run && !a.rolled_back && (
              <Link to={`/audits/${auditId}/actions/${a.action_id}/rollback`} className="rounded border border-warn px-2 py-1 text-xs font-semibold">
                {t("audit.rollback")}
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}
