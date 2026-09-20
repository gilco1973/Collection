import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useContract, usePage, usePageFindings, useRecordView, useReportProblem, useSignedIn } from "../api/hooks";
import { openChat } from "../chatBus";
import { FindingsList } from "../components/AuditParts";
import { StatusBadge, chip } from "../components/Badges";
import Markdown from "../components/Markdown";
import { stripLeadingHeading } from "../components/markdownLinks";
import SelectionToolbar from "../components/SelectionToolbar";
import { Card, ErrorBox, Loading, btnPrimary, input, label } from "../components/States";
import { isRtlContentLanguage, useContentLanguage } from "../contentLanguage";
import { formatDay } from "../format";
import { usePageTitle } from "../usePageTitle";

const CATEGORIES = ["outdated", "incorrect", "unclear", "broken-link", "sensitive-content", "other"];
const MAX_MESSAGE = 1000;

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-baseline gap-x-3 text-[13px]">
      <dt className="text-[12px] font-medium text-muted">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export default function PageView() {
  const { t, i18n } = useTranslation();
  const path = useParams()["*"] ?? "";
  const contentLang = useContentLanguage();
  const page = usePage(path, contentLang);
  const findings = usePageFindings(path);
  const report = useReportProblem(path);
  const [category, setCategory] = useState("outdated");
  const [message, setMessage] = useState("");
  const contract = useContract();
  const sentRef = useRef<HTMLParagraphElement>(null);
  const signedIn = useSignedIn();
  const { mutate: recordView } = useRecordView();
  const recorded = useRef<string | null>(null);
  const [search, setSearch] = useSearchParams();
  const articleRef = useRef<HTMLElement>(null);
  const quizzed = useRef<string | null>(null);
  usePageTitle(page.data?.meta.title);
  useEffect(() => {
    if (report.isSuccess) sentRef.current?.focus();
  }, [report.isSuccess]);
  useEffect(() => {
    // A signed-in reader's progress: once per page open, never for a withheld page (there was nothing to read).
    if (!signedIn || !page.data || page.data.withheld || recorded.current === path) return;
    recorded.current = path;
    recordView(path);
  }, [signedIn, page.data, path, recordView]);
  useEffect(() => {
    // Opened with `?quiz=1` (a nudge): once the page is in, drop the flag from the URL and ask for one whole-page
    // quiz — unless the page is withheld (there is nothing to quiz on).
    if (search.get("quiz") !== "1" || !page.data || quizzed.current === path) return;
    quizzed.current = path;
    setSearch((prev) => { const next = new URLSearchParams(prev); next.delete("quiz"); return next; }, { replace: true });
    if (!page.data.withheld) openChat({ mode: "quiz", context: { path: page.data.meta.path, title: page.data.meta.title } });
  }, [search, setSearch, page.data, path]);
  if (page.isPending) return <Loading />;
  if (page.error) return <ErrorBox error={page.error} onRetry={() => page.refetch()} />;
  const { meta } = page.data;
  const na = t("common.notAvailable");
  const rtl = page.data.translated && isRtlContentLanguage(contentLang);
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <article ref={articleRef} className="motion-safe:animate-rise-slow min-w-0 break-words rounded border border-rule bg-surface px-6 py-6 shadow-1 md:px-8">
        <p className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
          <Link to="/kb" className="hover:text-ink">{t("nav.browse")}</Link>
          {page.data.section && <><span aria-hidden="true">/</span><Link to={`/kb/${page.data.section.id}`} className="hover:text-ink">{page.data.section.title}</Link></>}
          <span aria-hidden="true">/</span>
          <span dir="ltr" className="font-mono text-[11px] text-faint">{meta.path}</span>
        </p>
        <h1 dir={rtl ? "rtl" : undefined} className="mt-3 text-[26px] font-semibold leading-[1.15] tracking-[-0.02em]" style={{ textWrap: "balance" }}>{meta.title}</h1>
        {contentLang !== "en" && !page.data.translated && !page.data.withheld && (
          <p role="status" className="mt-3 rounded-s bg-surface-3 px-3 py-2 text-[13px] text-muted">{t("page.notYetTranslated")}</p>
        )}
        {meta.frontmatter_error && <p role="alert" className="mt-3 rounded-s bg-warn-soft p-2 text-[13px] text-warn">{t("page.frontmatterError", { error: meta.frontmatter_error })}</p>}
        {page.data.withheld ? (
          <div role="alert" className="mt-5 rounded border border-crit/30 bg-crit-soft p-4 text-crit">
            <p className="font-semibold">{t("page.withheld")}</p>
            <p className="text-[13px]">{t("page.withheldHelp")}</p>
          </div>
        ) : (
          <div dir={rtl ? "rtl" : undefined} className="mt-4 text-[14px] leading-[1.6] text-ink-2">
            <Markdown source={stripLeadingHeading(page.data.body_markdown ?? "", meta.title)} basePath={meta.path} catalogFiles={contract.data?.catalogs.map((c) => c.path)} />
          </div>
        )}
      </article>
      {!page.data.withheld && <SelectionToolbar articleRef={articleRef} path={meta.path} title={meta.title} />}
      <aside className="flex flex-col gap-5">
        <Card title={t("page.about")}>
          <dl className="flex flex-col gap-2">
            <Row k={t("page.owner")}><span className="font-mono text-[12px]">{meta.owner ?? na}</span></Row>
            <Row k={t("page.status")}><StatusBadge status={meta.status} /></Row>
            <Row k={t("page.reviewed")}>{formatDay(meta.reviewed, i18n.language) || na}</Row>
            <Row k={t("page.nextReview")}>{formatDay(meta.next_review, i18n.language) || na}{meta.stale && <span className={`${chip} ms-2 bg-warn-soft text-warn`}>{t("page.stale")}</span>}</Row>
            <Row k={t("page.tags")}><span className="flex flex-wrap gap-1">{meta.tags.length ? meta.tags.map((x) => <span key={x} className={`${chip} bg-r-soft text-r`}>{x}</span>) : na}</span></Row>
            <Row k={t("page.audience")}><span className="flex flex-wrap gap-1">{meta.audience.length ? meta.audience.map((x) => <span key={x} className={`${chip} bg-accent-soft text-accent-ink`}>{x}</span>) : na}</span></Row>
          </dl>
        </Card>
        <Card title={t("page.findings")}>
          {findings.isPending ? <Loading /> : findings.error ? <ErrorBox error={findings.error} onRetry={() => findings.refetch()} /> : findings.data?.items.length ? <FindingsList findings={findings.data.items} /> : <p className="text-[13px] text-muted">{t("page.noFindings")}</p>}
        </Card>
        <Card title={t("page.reportProblem")}>
          {report.isSuccess ? (
            <p ref={sentRef} tabIndex={-1} role="status" className="motion-safe:animate-scale-in rounded text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-accent">{t("page.reportSent", { owner: report.data.owner ?? na })}</p>
          ) : (
            <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); report.mutate({ category, message }); }}>
              <label className={label}>{t("page.reportCategory")}
                <select className={`${input} mt-1`} value={category} onChange={(e) => setCategory(e.target.value)}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{t(`page.categories.${c}`)}</option>)}
                </select>
              </label>
              <label className={label}>{t("page.reportMessage")}
                <textarea className={`${input} mt-1 h-auto min-h-[72px] py-2`} rows={3} minLength={10} maxLength={MAX_MESSAGE} required value={message} onChange={(e) => setMessage(e.target.value)} />
              </label>
              <p className="text-[12px] text-muted">{t("page.reportMessageHelp", { max: MAX_MESSAGE })}</p>
              {report.error && <ErrorBox error={report.error} />}
              <div><button type="submit" disabled={report.isPending} className={btnPrimary}>{t("page.send")}</button></div>
            </form>
          )}
        </Card>
      </aside>
    </div>
  );
}
