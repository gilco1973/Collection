import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useAudits, useMe, usePagesFor, useProfile, useSections, useSignedIn, useStalePages } from "../api/hooks";
import { ModeBadge, StatusBadge, chip } from "../components/Badges";
import PersonaPicker from "../components/PersonaPicker";
import { Card, Empty, ErrorBox, Loading, btn } from "../components/States";
import VoiceInputButton from "../components/VoiceInputButton";
import { useContentLanguage } from "../contentLanguage";
import { formatDate } from "../format";
import { usePageTitle } from "../usePageTitle";

const FOR_YOU_LIMIT = 8;

export default function Home() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const contentLang = useContentLanguage();
  const me = useMe();
  const sections = useSections(contentLang);
  const stale = useStalePages(contentLang);
  const audits = useAudits({ page_size: "1" });
  const profile = useProfile(useSignedIn());
  const persona = profile.data?.persona ?? null;
  const forYou = usePagesFor(persona, contentLang);
  const [q, setQ] = useState("");
  const [skipped, setSkipped] = useState(false);
  const [changing, setChanging] = useState(false);
  usePageTitle(t("home.title"));
  const latest = audits.data?.items[0];
  const first = sections.data?.[0];
  const operator = me.data?.role === "operator";
  const recent = Object.entries(profile.data?.viewed ?? {}).sort((a, b) => b[1].last_at.localeCompare(a[1].last_at)).slice(0, 5);
  const progressFor = (id: string) => profile.data?.progress.find((p) => p.section === id);
  const forYouIn = (id: string) => forYou.data?.items.filter((p) => p.section === id).length ?? 0;
  // Sections with pages for the reader's persona come first; the rest keep the contract's order (sort is stable).
  const ordered = [...(sections.data ?? [])].sort((a, b) => Number(forYouIn(b.id) > 0) - Number(forYouIn(a.id) > 0));
  return (
    <div className="flex flex-col gap-7">
      <section className="motion-safe:animate-rise-slow relative flex flex-col gap-4 overflow-hidden rounded-l border border-rule bg-surface px-6 py-7 shadow-1 md:px-10 md:py-9">
        <h1 className="max-w-[24ch] text-[26px] font-semibold leading-[1.15] tracking-[-0.02em] md:text-[30px]" style={{ textWrap: "balance" }}>{t("home.title")}</h1>
        <p className="max-w-[60ch] text-[15px] text-muted">{t("home.subtitle")}</p>
        <form role="search" onSubmit={(e) => { e.preventDefault(); navigate(`/search?q=${encodeURIComponent(q)}`); }} className="mt-1 flex h-[52px] max-w-[760px] items-center gap-3 rounded-[10px] border border-rule-2 bg-surface px-4 shadow-1 focus-within:ring-2 focus-within:ring-accent">
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("home.searchPlaceholder")} aria-label={t("search.title")} className="h-full w-full bg-transparent text-[15px] text-ink placeholder:text-faint focus:outline-none" />
          <VoiceInputButton onResult={(text) => { setQ(text); navigate(`/search?q=${encodeURIComponent(text)}`); }} />
          <kbd className="hidden rounded border border-rule-2 border-b-2 bg-surface px-1.5 font-mono text-[10.5px] leading-4 text-muted md:inline">↵</kbd>
        </form>
        <div className="flex flex-wrap gap-2">
          <Link to={first ? `/kb/${first.id}` : "/kb"} className={btn}>{t("home.startReading")}</Link>
          {operator && <Link to="/audits/new" className={btn}>{t("home.runAudit")}</Link>}
        </div>
      </section>
      {profile.data && persona === null && !skipped && (
        <Card title={t("persona.choose")} className="motion-safe:animate-rise-slow">
          <div className="flex flex-col gap-3" data-testid="persona-choose">
            <p className="max-w-[70ch] text-[13px] text-muted">{t("persona.chooseHelp")}</p>
            <PersonaPicker profile={profile.data} onDone={() => setSkipped(true)} />
          </div>
        </Card>
      )}
      {profile.data && persona && (
        <Card title={t("persona.forYou", { label: t(`persona.labels.${persona}`, { defaultValue: persona }) })} sub={t("persona.forYouSub")}
          actions={<button type="button" onClick={() => setChanging((v) => !v)} aria-expanded={changing} className={btn}>{t("persona.change")}</button>}>
          <div className="flex flex-col gap-3" data-testid="persona-for-you">
            {changing && <div className="border-b border-rule pb-3"><PersonaPicker profile={profile.data} onDone={() => setChanging(false)} /></div>}
            {forYou.isPending ? <Loading /> : forYou.error ? <ErrorBox error={forYou.error} onRetry={() => forYou.refetch()} /> : !forYou.data?.items.length ? (
              <Empty text={t("persona.forYouEmpty")} />
            ) : (
              <ul className="divide-y divide-rule text-[13px]" data-testid="for-you">
                {forYou.data.items.slice(0, FOR_YOU_LIMIT).map((p) => (
                  <li key={p.path} className="flex items-center justify-between gap-2 py-2">
                    <Link to={`/kb/page/${p.path}`} className="text-accent hover:underline">{p.title}</Link>
                    <span className="flex shrink-0 items-center gap-2">
                      {profile.data?.viewed[p.path] && <span className={`${chip} bg-ok-soft text-ok`}>{t("profile.viewed")}</span>}
                      <span className="font-mono text-[11px] text-faint" dir="ltr">{p.path}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      )}
      {recent.length > 0 && (
        <Card title={t("profile.continueReading")} sub={t("profile.continueReadingSub")}>
          <ul className="divide-y divide-rule text-[13px]" data-testid="continue-reading">
            {recent.map(([path, visit]) => (
              <li key={path} className="flex items-center justify-between gap-2 py-2">
                <Link to={`/kb/page/${path}`} className="text-accent hover:underline">{visit.title}</Link>
                <span className="font-mono text-[11px] text-faint" dir="ltr">{path}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title={t("home.sections")} sub={t("home.sectionsSub")}>
        {sections.isPending ? <Loading /> : sections.error ? <ErrorBox error={sections.error} onRetry={() => sections.refetch()} /> : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="sections">
            {ordered.map((s, i) => (
              <li key={s.id} className="motion-safe:animate-rise" style={{ animationDelay: `${Math.min(i * 30, 240)}ms` }}>
                <Link to={`/kb/${s.id}`} className="flex h-full flex-col gap-1 rounded border border-rule bg-surface-2 p-3.5 transition hover:-translate-y-px hover:border-rule-2 hover:bg-surface hover:shadow-1">
                  <span className="text-[13px] font-semibold">{s.title}</span>
                  <span className="text-[12px] text-muted">
                    {t("home.pages", { count: s.page_count })}{s.stale_count ? ` · ${t("home.stale", { count: s.stale_count })}` : ""}
                    {progressFor(s.id)?.total ? ` · ${t("profile.progress", { viewed: progressFor(s.id)!.viewed, total: progressFor(s.id)!.total })}` : ""}
                    {forYouIn(s.id) ? ` · ${t("persona.forYouCount", { count: forYouIn(s.id) })}` : ""}
                  </span>
                  <span className="mt-1 font-mono text-[11px] text-faint">{s.owner}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <div className="grid gap-7 md:grid-cols-2">
        <Card title={t("home.latestAudit")}>
          {audits.isPending ? <Loading /> : audits.error ? <ErrorBox error={audits.error} onRetry={() => audits.refetch()} /> : !latest ? (
            <Empty text={t("home.noAudits")} />
          ) : (
            <Link to={`/audits/${latest.audit_id}`} className="flex flex-col gap-2 rounded hover:bg-surface-2">
              <div className="flex flex-wrap items-center gap-2">
                <ModeBadge dryRun={latest.dry_run} />
                <StatusBadge status={latest.status} />
                <span className="font-mono text-[12px] text-muted" dir="ltr">{latest.audit_id}</span>
              </div>
              <p className="text-[13px]">
                {t("home.findings", { count: latest.issues_found })} · {t("home.reviewQueue", { count: latest.manual_review_needed })}
              </p>
              <p className="text-[12px] text-muted">{formatDate(latest.audit_date, i18n.language)}</p>
            </Link>
          )}
        </Card>
        <Card title={t("home.stalePages")}>
          {stale.isPending ? <Loading /> : stale.error ? <ErrorBox error={stale.error} onRetry={() => stale.refetch()} /> : !stale.data?.items.length ? (
            <Empty text={t("home.noStale")} />
          ) : (
            <ul className="divide-y divide-rule text-[13px]">
              {stale.data.items.slice(0, 8).map((p) => (
                <li key={p.path} className="flex items-center justify-between gap-2 py-2">
                  <Link to={`/kb/page/${p.path}`} className="text-accent hover:underline">{p.title}</Link>
                  <span className="font-mono text-[11px] text-faint">{p.owner}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {operator && (
        <section className="motion-safe:animate-rise-slow grid gap-5 rounded-l bg-emphasis px-7 py-6 text-on-emphasis md:grid-cols-[1.2fr_1fr] md:items-center">
          <div className="flex flex-col gap-2">
            <h2 className="text-[20px] font-semibold tracking-[-0.01em] text-on-emphasis">{t("home.bandTitle")}</h2>
            <p className="text-[13.5px] leading-[1.5] text-on-emphasis-muted">{t("home.bandBody")}</p>
          </div>
          <div className="flex md:justify-end">
            <Link to="/audits/new" className="inline-flex h-8 items-center rounded-s border border-on-emphasis bg-on-emphasis px-3 text-[13px] font-semibold text-emphasis">{t("home.runAudit")}</Link>
          </div>
        </section>
      )}
    </div>
  );
}
