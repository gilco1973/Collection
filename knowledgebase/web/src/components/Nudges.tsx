import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { useMe, useProfile, useSections } from "../api/hooks";
import { useContentLanguage } from "../contentLanguage";
import { computeNudges, type NudgeKind } from "../nudges";
import { dismissNudge, setNudgesEnabled, useNudgeState } from "../nudgeStore";
import { btn } from "./States";

const ICONS: Record<NudgeKind, string> = {
  resume: "M6 3h12v18l-6-4-6 4z",
  quiz: "m9 12 2 2 4-4M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z",
  section: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  welcome: "M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8",
};

function Icon({ kind }: { kind: NudgeKind }) {
  return (
    <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-s bg-accent-soft text-accent-ink">
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d={ICONS[kind]} />
      </svg>
    </span>
  );
}

const dismissClass = "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-s text-muted transition hover:bg-surface-3 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/**
 * The proactive librarian: a compact, dismissible strip with up to two suggestions worked out in the browser
 * from the profile and section list the reader already has. Signed-in readers with suggestions enabled only;
 * nothing is fetched or stored for anyone else, and nothing new leaves the browser for anyone.
 */
export default function Nudges() {
  const me = useMe();
  const sub = me.data?.user?.sub;
  const state = useNudgeState(sub);
  if (!sub || !state.enabled) return null;
  return <Strip sub={sub} dismissed={state.dismissed} />;
}

function Strip({ sub, dismissed }: { sub: string; dismissed: Record<string, string> }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const lang = useContentLanguage();
  const profile = useProfile(true);
  const sections = useSections(lang);
  const strip = useRef<HTMLElement>(null);
  const nudges = profile.data && sections.data
    ? computeNudges({ profile: profile.data, sections: sections.data, now: Date.now(), dismissed, currentPath: pathname, t: (key, params) => t(key, params) })
    : [];
  const dismiss = (id: string) => {
    dismissNudge(sub, id);
    // The focused button is about to unmount: land on what is left of the strip, else on the page body.
    queueMicrotask(() => (strip.current?.querySelector<HTMLElement>("a, button") ?? document.getElementById("main"))?.focus());
  };
  if (nudges.length === 0) return null;
  return (
    <section ref={strip} role="region" aria-label={t("nudges.label")} className="border-b border-rule bg-surface-2" data-testid="nudges">
      <ul className="mx-auto flex max-w-wrap flex-col gap-2 px-4 py-2.5 md:flex-row md:gap-3 lg:px-10">
        {nudges.map((n) => (
          <li key={n.id} className="motion-safe:animate-rise flex min-w-0 flex-1 items-center gap-2.5 rounded border border-rule bg-surface px-3 py-2 shadow-1">
            <Icon kind={n.kind} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold text-ink">{n.title}</span>
              <span className="line-clamp-2 text-[12px] leading-[1.4] text-muted">{n.body}</span>
            </span>
            <Link to={n.to} className={btn} data-testid={`nudge-${n.kind}`} aria-label={t("nudges.openLabel", { title: n.title })}>{t("nudges.open")}</Link>
            <button type="button" onClick={() => dismiss(n.id)} aria-label={t("nudges.dismiss", { title: n.title })} className={dismissClass}>
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The Settings switch for the strip. The preference lives in this browser only, per reader. */
export function SuggestionsToggle({ sub }: { sub: string }) {
  const { t } = useTranslation();
  const { enabled } = useNudgeState(sub);
  return (
    <div className="flex items-center gap-3">
      <button type="button" role="switch" aria-checked={enabled} aria-label={t("nudges.settingsTitle")} onClick={() => setNudgesEnabled(sub, !enabled)}
        className={`flex h-6 w-11 shrink-0 items-center rounded-full border px-1 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${enabled ? "justify-end border-accent-ink bg-accent-soft" : "justify-start border-rule-2 bg-surface-3"}`}>
        <span aria-hidden="true" className={`h-4 w-4 rounded-full shadow-1 transition ${enabled ? "bg-accent-ink" : "bg-muted"}`} />
      </button>
      <span className="text-sm" data-testid="nudges-state">{enabled ? t("nudges.enabled") : t("nudges.disabled")}</span>
    </div>
  );
}
