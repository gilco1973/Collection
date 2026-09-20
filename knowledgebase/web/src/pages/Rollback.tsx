import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAudit, useRollback } from "../api/hooks";
import { ModeBadge } from "../components/Badges";
import ConfirmWithReason from "../components/ConfirmWithReason";
import { ErrorBox, Loading } from "../components/States";
import { usePageTitle } from "../usePageTitle";

export default function Rollback() {
  const { t } = useTranslation();
  const { id = "", actionId = "" } = useParams();
  const navigate = useNavigate();
  const audit = useAudit(id);
  const rollback = useRollback(id, actionId);
  const [force, setForce] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  usePageTitle(t("rollback.title"));
  useEffect(() => {
    if (rollback.error) errorRef.current?.focus();
  }, [rollback.error]);
  if (audit.isPending) return <Loading />;
  if (audit.error) return <ErrorBox error={audit.error} onRetry={() => audit.refetch()} />;
  const action = audit.data.fixes_applied.find((a) => a.action_id === actionId);
  const back = <Link to={`/audits/${id}`} className="text-[13px] text-accent hover:underline">{t("common.back")}</Link>;
  if (!action) return <div className="space-y-4"><ErrorBox error={new Error(t("rollback.unknownAction", { id: actionId }))} />{back}</div>;
  const blocked = action.dry_run ? t("rollback.dryRunAction") : action.rolled_back ? t("rollback.alreadyRolledBack") : null;
  return (
    <div className="motion-safe:animate-rise-slow mx-auto max-w-xl space-y-4 rounded-l border border-warn bg-surface p-5 shadow-1">
      <div className="flex flex-wrap items-center gap-2">
        <ModeBadge dryRun={false} large />
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{t("rollback.title")} <span dir="ltr" className="break-all font-mono text-[15px] text-muted">{action.action_id}</span></h1>
      </div>
      <p className="rounded-s bg-warn-soft px-3 py-2 text-[13px] font-medium text-warn">{t("rollback.editsNow")}</p>
      <p className="text-sm">
        <span className="font-mono text-xs">{action.action_type}</span> <span dir="ltr" className="font-mono">{action.path}</span>
        <br />{action.description}
      </p>
      {blocked ? (
        <p role="status" className="rounded bg-surface-3 p-3 text-sm">{blocked}</p>
      ) : (
        <>
          <div ref={errorRef} tabIndex={-1} className="outline-none">{rollback.error && <ErrorBox error={rollback.error} />}</div>
          <ConfirmWithReason inline
            title={t("rollback.confirmTitle")} description={t("rollback.help")} token="ROLLBACK" confirmLabel={t("rollback.confirm")} busy={rollback.isPending}
            extra={
              <label className="mt-3 block text-sm">
                <input type="checkbox" className="me-2" checked={force} onChange={(e) => setForce(e.target.checked)} />{t("rollback.force")}
                <span className="block text-xs text-muted">{t("rollback.forceHelp")}</span>
              </label>
            }
            onConfirm={(reason) => rollback.mutate({ reason, force }, { onSuccess: () => navigate(`/audits/${id}?tab=actions`) })}
            onCancel={() => navigate(`/audits/${id}?tab=actions`)}
          />
        </>
      )}
      {back}
    </div>
  );
}
