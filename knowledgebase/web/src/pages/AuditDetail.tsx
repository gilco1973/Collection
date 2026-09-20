import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useAudit, useMe } from "../api/hooks";
import AuditHeader from "../components/AuditHeader";
import { ActionsList, FindingsList } from "../components/AuditParts";
import { ReviewQueue, ToolTrail } from "../components/AuditTrail";
import Markdown from "../components/Markdown";
import { Card, ErrorBox, Loading } from "../components/States";
import Tabs from "../components/Tabs";
import { usePageTitle } from "../usePageTitle";

const TABS = ["findings", "actions", "review", "trail", "summary"] as const;
type Tab = (typeof TABS)[number];
const isTab = (value: string | null): value is Tab => TABS.includes(value as Tab);

export default function AuditDetail() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: Tab = isTab(requested) ? requested : "findings";
  const me = useMe();
  const audit = useAudit(id);
  usePageTitle(id);
  if (audit.isPending) return <Loading />;
  if (audit.error) return <ErrorBox error={audit.error} onRetry={() => audit.refetch()} />;
  const a = audit.data;
  const operator = me.data?.role === "operator";
  const forced = (location.state as { forced?: boolean } | null)?.forced;
  const setTab = (next: Tab) => {
    const search = new URLSearchParams(params);
    search.set("tab", next);
    setParams(search, { replace: true });
  };
  return (
    <div className="space-y-4">
      <AuditHeader audit={a} operator={!!operator} forced={forced} />
      <Tabs tabs={TABS.map((k) => ({ key: k, label: t(`audit.tabs.${k}`) }))} current={tab} label={t("audits.title")} onChange={setTab}>
        <Card>
          {tab === "findings" && <FindingsList findings={a.findings} />}
          {tab === "actions" && <ActionsList actions={a.fixes_applied} auditId={a.audit_id} canRollback={!!operator} />}
          {tab === "review" && <ReviewQueue items={a.manual_review_needed} />}
          {tab === "trail" && <ToolTrail calls={a.tool_calls} />}
          {tab === "summary" && (a.ai_summary ? <Markdown source={a.ai_summary} basePath="index.md" plainLinks /> : <p className="text-sm text-muted">{t("audit.summaryEmpty")}</p>)}
        </Card>
      </Tabs>
      <Link to="/audits" className="text-[13px] text-accent hover:underline">{t("common.back")}</Link>
    </div>
  );
}
