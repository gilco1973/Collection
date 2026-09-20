import { useTranslation } from "react-i18next";
import { useInsights, useRefreshInsights } from "../api/hooks";
import type { Insights, PageInsight } from "../api/insightsTypes";
import { formatDate } from "../format";
import { Empty, ErrorBox, Loading, btn } from "./States";

const TOP = 10;
const th = "whitespace-nowrap border-b border-rule px-3 py-2 text-start text-[11px] font-semibold uppercase tracking-[0.04em] text-muted";
const thEnd = `${th} text-end`;
const td = "px-3 py-2 align-middle";
const tdEnd = `${td} text-end tabular-nums`;
const h2 = "text-[15px] font-semibold tracking-[-0.01em]";

type Row = [string, PageInsight];
const total = (page: PageInsight) => Object.values(page.problems).reduce((sum, n) => sum + n, 0);
const byProblems = (pages: Record<string, PageInsight>): Row[] =>
  Object.entries(pages).filter(([, p]) => total(p) > 0).sort((a, b) => total(b[1]) - total(a[1]) || a[0].localeCompare(b[0])).slice(0, TOP);
const byFailRate = (pages: Record<string, PageInsight>): Row[] =>
  Object.entries(pages).filter(([, p]) => p.quiz_fail_rate !== null).sort((a, b) => (b[1].quiz_fail_rate ?? 0) - (a[1].quiz_fail_rate ?? 0) || a[0].localeCompare(b[0])).slice(0, TOP);

function Table({ caption, head, children, empty }: { caption: string; head: React.ReactNode; children: React.ReactNode[]; empty: string }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className={h2}>{caption}</h2>
      {children.length ? (
        <div className="overflow-x-auto rounded border border-rule bg-surface shadow-1">
          <table className="min-w-full text-[12.5px]">
            <caption className="sr-only">{caption}</caption>
            <thead><tr>{head}</tr></thead>
            <tbody className="divide-y divide-rule">{children}</tbody>
          </table>
        </div>
      ) : (
        <p className="text-[13px] text-muted">{empty}</p>
      )}
    </section>
  );
}

function Tables({ data }: { data: Insights }) {
  const { t, i18n } = useTranslation();
  const hidden = t("insights.hidden");
  const num = (value: number | null) => (value === null ? <span className="text-faint">{hidden}</span> : value);
  const percent = (value: number) => {
    try {
      return new Intl.NumberFormat(i18n.language, { style: "percent", maximumFractionDigits: 0 }).format(value);
    } catch {
      return `${Math.round(value * 100)}%`;
    }
  };
  const categories = (page: PageInsight) => Object.entries(page.problems).sort((a, b) => b[1] - a[1]).map(([name, n]) => `${name} ${n}`).join(", ");
  const unanswered = (["mode", "lang"] as const).flatMap((dimension) =>
    Object.entries(data.unanswered[dimension] ?? {}).sort((a, b) => b[1] - a[1]).map(([value, n]) => ({ dimension, value, n })),
  );
  return (
    <div className="flex flex-col gap-6">
      <p className="text-[13px] text-muted">
        {t("insights.generated", { date: formatDate(data.generated_at, i18n.language), days: data.window_days })}
        {" · "}
        {t("insights.kNote", { k: data.k, suppressed: data.suppressed })}
      </p>
      <Table caption={t("insights.byProblems")} empty={t("insights.none")}
        head={<><th scope="col" className={th}>{t("insights.page")}</th><th scope="col" className={thEnd}>{t("insights.problems")}</th><th scope="col" className={th}>{t("insights.categories")}</th><th scope="col" className={thEnd}>{t("insights.readers")}</th><th scope="col" className={thEnd}>{t("insights.views")}</th><th scope="col" className={thEnd}>{t("insights.citations")}</th></>}>
        {byProblems(data.pages).map(([path, page]) => (
          <tr key={path}>
            <td className={`${td} font-mono text-[12px]`} dir="ltr">{path}</td>
            <td className={tdEnd}>{total(page)}</td>
            <td className={`${td} text-ink-2`}>{categories(page)}</td>
            <td className={tdEnd}>{num(page.readers)}</td>
            <td className={tdEnd}>{num(page.views)}</td>
            <td className={tdEnd}>{page.chat_citations}</td>
          </tr>
        ))}
      </Table>
      <Table caption={t("insights.byQuizFail")} empty={t("insights.none")}
        head={<><th scope="col" className={th}>{t("insights.page")}</th><th scope="col" className={thEnd}>{t("insights.failRate")}</th><th scope="col" className={thEnd}>{t("insights.attempts")}</th><th scope="col" className={thEnd}>{t("insights.readers")}</th></>}>
        {byFailRate(data.pages).map(([path, page]) => (
          <tr key={path}>
            <td className={`${td} font-mono text-[12px]`} dir="ltr">{path}</td>
            <td className={tdEnd}>{percent(page.quiz_fail_rate ?? 0)}</td>
            <td className={tdEnd}>{num(page.quiz_attempts)}</td>
            <td className={tdEnd}>{num(page.readers)}</td>
          </tr>
        ))}
      </Table>
      <Table caption={t("insights.unanswered")} empty={t("insights.none")}
        head={<><th scope="col" className={th}>{t("insights.dimension")}</th><th scope="col" className={th}>{t("insights.value")}</th><th scope="col" className={thEnd}>{t("insights.count")}</th></>}>
        {unanswered.map(({ dimension, value, n }) => (
          <tr key={`${dimension}-${value}`}>
            <td className={`${td} text-ink-2`}>{t(`insights.${dimension}`)}</td>
            <td className={td}>{value}</td>
            <td className={tdEnd}>{n}</td>
          </tr>
        ))}
      </Table>
    </div>
  );
}

/** Operator view of "which pages confuse people": three small tables from the stored insights, and a refresh. */
export default function InsightsPanel() {
  const { t } = useTranslation();
  const insights = useInsights(true);
  const refresh = useRefreshInsights();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-muted">{t("insights.intro")}</p>
        <button type="button" className={btn} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          {refresh.isPending ? t("insights.refreshing") : t("insights.refresh")}
        </button>
      </div>
      {refresh.error && <ErrorBox error={refresh.error} />}
      {insights.isPending ? <Loading /> : insights.error ? <ErrorBox error={insights.error} onRetry={() => insights.refetch()} /> : insights.data ? (
        <Tables data={insights.data} />
      ) : (
        <Empty text={t("insights.empty")} />
      )}
    </div>
  );
}
