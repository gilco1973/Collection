import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { useAudits, useMe } from "../api/hooks";
import { ModeBadge, StatusBadge } from "../components/Badges";
import InsightsPanel from "../components/InsightsPanel";
import { Empty, ErrorBox, Loading, btn, btnPrimary } from "../components/States";
import Tabs from "../components/Tabs";
import { formatDate, formatMoney } from "../format";
import { usePageTitle } from "../usePageTitle";

const PAGE_SIZE = 20;
const TABS = ["list", "insights"] as const;
type Tab = (typeof TABS)[number];
const FILTERS = [
  { key: "mode", label: "audits.filterMode", options: ["dry", "live"], i18n: (v: string) => `mode.${v}` },
  { key: "status", label: "audits.filterStatus", options: ["in_progress", "completed", "failed", "cancelled"], i18n: (v: string) => `status.${v}` },
  { key: "type", label: "audits.filterType", options: ["agent", "offline"], i18n: (v: string) => `audits.types.${v}` },
];
const select = "h-[34px] rounded-s border border-rule-2 bg-surface px-2 text-[13px] text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent";
const th = "whitespace-nowrap border-b border-rule px-3 py-2 text-start text-[11px] font-semibold uppercase tracking-[0.04em] text-muted";
const thEnd = `${th} text-end`;
const td = "px-3 py-2.5 align-middle";

export default function Audits() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  usePageTitle(t("audits.title"));
  const operator = useMe().data?.role === "operator";
  const tab: Tab = operator && params.get("tab") === "insights" ? "insights" : "list"; // the Insights tab is operator-only
  const setTab = (next: Tab) => {
    const search = new URLSearchParams(params);
    if (next === "insights") search.set("tab", next);
    else search.delete("tab");
    setParams(search, { replace: true });
  };
  const page = Math.max(1, Number(params.get("page")) || 1);
  const filters = Object.fromEntries(FILTERS.map((f) => [f.key, params.get(f.key) || undefined]));
  const audits = useAudits({ ...filters, page: String(page), page_size: String(PAGE_SIZE) });
  const pages = Math.max(1, Math.ceil((audits.data?.total ?? 0) / PAGE_SIZE));
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };
  const list = (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-3 text-[12px] font-medium text-muted">
        {FILTERS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">{t(f.label)}
            <select className={select} value={filters[f.key] ?? ""} onChange={(e) => update(f.key, e.target.value)}>
              <option value="">{t("audits.all")}</option>
              {f.options.map((o) => <option key={o} value={o}>{t(f.i18n(o))}</option>)}
            </select>
          </label>
        ))}
      </div>
      {audits.isPending ? <Loading /> : audits.error ? <ErrorBox error={audits.error} onRetry={() => audits.refetch()} /> : !audits.data.items.length ? (
        <Empty text={t("audits.noAudits")} />
      ) : (
        <div className={`overflow-x-auto rounded border border-rule bg-surface shadow-1 ${audits.isPlaceholderData ? "opacity-60" : ""}`} aria-busy={audits.isPlaceholderData}>
          <table className="min-w-full text-[12.5px]">
            <caption className="sr-only">{t("audits.tableCaption")}</caption>
            <thead>
              <tr>
                <th scope="col" className={th}>{t("audits.id")}</th><th scope="col" className={th}>{t("audits.mode")}</th><th scope="col" className={th}>{t("audits.status")}</th>
                <th scope="col" className={th}>{t("audits.date")}</th><th scope="col" className={thEnd}>{t("audits.findings")}</th><th scope="col" className={thEnd}>{t("audits.fixes")}</th>
                <th scope="col" className={thEnd}>{t("audits.denied")}</th><th scope="col" className={thEnd}>{t("audits.cost")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {audits.data.items.map((a, i) => (
                <tr key={a.audit_id} className="motion-safe:animate-fade-in hover:bg-surface-2" style={{ animationDelay: `${Math.min(i * 15, 200)}ms` }}>
                  <td className={td}><Link to={`/audits/${a.audit_id}`} dir="ltr" className="font-mono text-[12px] font-medium text-accent hover:underline">{a.audit_id}</Link><span className="ms-2 text-[11px] text-muted">{t(`audits.types.${a.audit_type}`)}</span></td>
                  <td className={td}><ModeBadge dryRun={a.dry_run} /></td>
                  <td className={td}><StatusBadge status={a.status} /></td>
                  <td className={`${td} whitespace-nowrap text-ink-2`}>{formatDate(a.audit_date, i18n.language)}</td>
                  <td className={`${td} text-end tabular-nums`}>{a.issues_found}</td>
                  <td className={`${td} text-end tabular-nums`}>{a.fixes_applied}{a.fixes_proposed ? ` (+${a.fixes_proposed})` : ""}</td>
                  <td className={`${td} text-end tabular-nums`}>{a.denied_calls}</td>
                  <td className={`${td} text-end font-mono tabular-nums`} dir="ltr">{formatMoney(a.total_cost_usd, i18n.language)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {audits.data && audits.data.total > PAGE_SIZE && (
        <nav aria-label={t("audits.pagination")} className="flex items-center gap-3 text-[13px]">
          <button type="button" disabled={page <= 1} onClick={() => update("page", String(page - 1))} className={btn}>{t("audits.prev")}</button>
          <span className="text-muted">{t("audits.page", { page, pages })}</span>
          <button type="button" disabled={page >= pages} onClick={() => update("page", String(page + 1))} className={btn}>{t("audits.next")}</button>
        </nav>
      )}
    </div>
  );
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{t("audits.title")}</h1>
        <Link to="/audits/new" className={btnPrimary}>{t("audits.new")}</Link>
      </div>
      {operator ? (
        <Tabs tabs={TABS.map((k) => ({ key: k, label: t(k === "list" ? "insights.auditsTab" : "insights.tab") }))} current={tab} label={t("insights.tablist")} onChange={setTab}>
          {tab === "insights" ? <InsightsPanel /> : list}
        </Tabs>
      ) : list}
    </div>
  );
}
