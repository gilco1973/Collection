import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useContract, useMe } from "../api/hooks";
import ChatWidget from "./ChatWidget";
import ContentLanguageSwitcher from "./ContentLanguageSwitcher";
import Identity from "./Identity";
import LanguageSwitcher from "./LanguageSwitcher";
import Nudges from "./Nudges";

/** `operator` links are hidden from viewers — a display choice only; the API enforces the role. */
const links = [
  { to: "/", key: "nav.home", end: true },
  { to: "/kb", key: "nav.browse" },
  { to: "/search", key: "nav.search" },
  { to: "/audits", key: "nav.audits", operator: true },
  { to: "/settings", key: "nav.settings" },
];

/** The mobile bar has one column per visible link; both class names must appear literally for Tailwind. */
const mobileColumns: Record<number, string> = { 4: "grid-cols-4", 5: "grid-cols-5" };

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-s px-3 py-2 text-[13px] font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
    isActive ? "bg-surface-3 text-ink" : "text-ink-2 hover:bg-surface-3 hover:text-ink"
  }`;

const mobileClass = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-11 min-w-0 items-center justify-center whitespace-normal break-words rounded-s px-1 py-1 text-center text-[11px] font-medium leading-tight focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
    isActive ? "bg-surface-3 text-ink" : "text-ink-2"
  }`;

/** The platform's mark: three stacked layers, the knowledge base as a stack of pages. */
function Mark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-6 w-6 rounded-[5px] bg-ink p-[3px] text-surface">
      <path d="M8 3 3.5 5.25 8 7.5l4.5-2.25zM3.5 8 8 10.25 12.5 8M3.5 10.5 8 12.75l4.5-2.25" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Layout() {
  const { t } = useTranslation();
  const me = useMe();
  const contract = useContract();
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current !== pathname) main.current?.focus();
    previous.current = pathname;
  }, [pathname]);
  const visible = links.filter((l) => !l.operator || me.data?.role === "operator");
  return (
    <div className="flex min-h-[100dvh] flex-col bg-bg text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:bg-surface focus:p-2">
        {t("app.skip")}
      </a>
      <header className="border-b border-rule bg-surface">
        <div className="mx-auto flex h-[60px] max-w-wrap items-center gap-6 px-4 lg:px-10">
          <NavLink to="/" className="flex min-w-0 shrink items-center gap-2.5 truncate text-[14px] font-semibold tracking-[-0.01em] text-ink">
            <Mark />
            <span className="truncate">{t("app.title")}</span>
          </NavLink>
          <nav aria-label={t("nav.primary")} className="hidden gap-1 md:flex">
            {visible.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={linkClass}>
                {t(l.key)}
              </NavLink>
            ))}
          </nav>
          <div className="ms-auto flex shrink-0 items-center gap-2 md:gap-3">
            {me.data && (
              <span className="inline-flex h-5 items-center rounded-[5px] bg-r-soft px-[7px] text-[11px] font-semibold tracking-[0.01em] text-r" data-testid="role">
                {t(`roles.${me.data.role}`)}
              </span>
            )}
            <Identity />
            <ContentLanguageSwitcher available={contract.data?.i18n.languages} />
            <LanguageSwitcher />
          </div>
        </div>
      </header>
      <Nudges />
      <main id="main" ref={main} tabIndex={-1} className="mx-auto w-full max-w-wrap flex-1 px-4 pb-24 pt-6 outline-none md:pb-10 lg:px-10 lg:pt-8">
        <Outlet />
      </main>
      <footer className="hidden border-t border-rule px-10 py-4 text-[12px] text-muted md:block">
        <div className="mx-auto flex max-w-wrap gap-4">
          <span>{t("app.tagline")}</span>
        </div>
      </footer>
      <nav aria-label={t("nav.primary")} className={`fixed inset-x-0 bottom-0 grid ${mobileColumns[visible.length]} gap-1 border-t border-rule bg-surface p-1 pb-[max(0.25rem,env(safe-area-inset-bottom))] md:hidden`}>
        {visible.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={mobileClass}>
            {t(l.key)}
          </NavLink>
        ))}
      </nav>
      <ChatWidget />
    </div>
  );
}
