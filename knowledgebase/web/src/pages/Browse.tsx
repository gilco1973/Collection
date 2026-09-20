import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useProfile, useSectionPages, useSections, useSignedIn } from "../api/hooks";
import type { PageSummary, Profile } from "../api/types";
import { StatusBadge, chip } from "../components/Badges";
import { Card, Empty, ErrorBox, Loading } from "../components/States";
import { useContentLanguage } from "../contentLanguage";
import { usePageTitle } from "../usePageTitle";

const GENERIC_AUDIENCE = "everyone";

/** A section's pages; `dimmed` renders the ones written for other audiences quieter, never hidden. */
function PageList({ items, profile, dimmed = false, testId }: { items: PageSummary[]; profile?: Profile; dimmed?: boolean; testId?: string }) {
  const { t } = useTranslation();
  return (
    <ul className={`divide-y divide-rule ${dimmed ? "opacity-70" : ""}`} data-testid={testId}>
      {items.map((p) => (
        <li key={p.path} className="flex items-center justify-between gap-3 py-2.5">
          <div className="flex min-w-0 flex-col">
            <Link to={`/kb/page/${p.path}`} className="truncate text-[13.5px] font-medium text-ink hover:text-accent hover:underline">{p.title}</Link>
            <span className="font-mono text-[11px] text-faint" dir="ltr">{p.path}</span>
          </div>
          <span className="flex shrink-0 items-center gap-2">
            {profile?.viewed[p.path] && <span className={`${chip} bg-ok-soft text-ok`}>{t("profile.viewed")}</span>}
            {p.stale && <span className={`${chip} bg-warn-soft text-warn`}>{t("browse.stale")}</span>}
            <StatusBadge status={p.status} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function Browse() {
  const { t } = useTranslation();
  const { section } = useParams();
  const contentLang = useContentLanguage();
  const sections = useSections(contentLang);
  const pages = useSectionPages(section, contentLang);
  const current = sections.data?.find((s) => s.id === section);
  const profile = useProfile(useSignedIn());
  const persona = profile.data?.persona ?? null;
  const progressFor = (id: string) => profile.data?.progress.find((p) => p.section === id);
  const forMe = (p: PageSummary) => p.audience.includes(persona!) || p.audience.includes(GENERIC_AUDIENCE);
  const items = pages.data?.items ?? [];
  const mine = persona ? items.filter(forMe) : items;
  const others = persona ? items.filter((p) => !forMe(p)) : [];
  usePageTitle(current?.title ?? t("browse.title"));
  const forYouTitle = persona ? t("persona.forYou", { label: t(`persona.labels.${persona}`, { defaultValue: persona }) }) : "";
  const groupHeading = "mb-1 text-[12px] font-semibold uppercase tracking-[0.04em] text-muted";
  return (
    <div className="grid gap-6 md:grid-cols-[232px_minmax(0,1fr)]">
      <nav aria-label={t("browse.title")} className="flex flex-col gap-0.5 md:border-e md:border-rule md:pe-4">
        <h1 className="px-2 pb-3 text-[20px] font-semibold tracking-[-0.01em]">{t("browse.title")}</h1>
        {sections.isPending ? <Loading /> : sections.error ? <ErrorBox error={sections.error} onRetry={() => sections.refetch()} /> : (
          <ul className="flex flex-col gap-0.5">
            {sections.data?.map((s, i) => (
              <li key={s.id} className="motion-safe:animate-rise" style={{ animationDelay: `${Math.min(i * 25, 200)}ms` }}>
                <Link to={`/kb/${s.id}`} aria-current={s.id === section ? "page" : undefined}
                  className={`flex h-8 items-center gap-2 rounded-s px-2 text-[13px] font-medium ${s.id === section ? "bg-surface-3 text-ink" : "text-ink-2 hover:bg-surface-3 hover:text-ink"}`}>
                  <span className="truncate">{s.title}</span>
                  <span className="ms-auto flex shrink-0 items-center gap-1.5">
                    {progressFor(s.id)?.total ? <span className="font-mono text-[11px] text-faint" data-testid={`progress-${s.id}`}>{progressFor(s.id)!.viewed}/{progressFor(s.id)!.total}</span> : null}
                    {s.stale_count > 0 && <span className={`${chip} bg-warn-soft text-warn`}>{s.stale_count}</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </nav>
      <div>
        {!section ? (
          <Empty />
        ) : (
          <Card title={current?.title ?? section} sub={current ? `${t("browse.owner")}: ${current.owner} · ${t("browse.reviewWindow")}: ${t("browse.days", { count: current.review_every_days })}` : undefined}>
            {pages.isPending ? <Loading /> : pages.error ? <ErrorBox error={pages.error} onRetry={() => pages.refetch()} /> : !items.length ? (
              <Empty text={t("browse.noPages")} />
            ) : !persona ? (
              <PageList items={items} profile={profile.data} />
            ) : (
              <div className="flex flex-col gap-4">
                {mine.length > 0 && (
                  <section aria-label={forYouTitle}>
                    <h3 className={groupHeading}>{forYouTitle}</h3>
                    <PageList items={mine} profile={profile.data} testId="for-you" />
                  </section>
                )}
                {others.length > 0 && (
                  <section aria-label={t("persona.otherAudiences")}>
                    <h3 className={groupHeading}>{t("persona.otherAudiences")}</h3>
                    <PageList items={others} profile={profile.data} dimmed testId="other-audiences" />
                  </section>
                )}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
