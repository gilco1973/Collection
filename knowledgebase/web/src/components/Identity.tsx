import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { signInUrl } from "../api/client";
import { useMe, useSignOut } from "../api/hooks";

const linkClass = "rounded-s px-2 py-1 text-[12px] font-medium text-ink-2 hover:bg-surface-3 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/**
 * Sign-in / signed-in controls for the header. Renders nothing until `/api/me` answers and nothing at
 * all on a server without single sign-on, so the console is unchanged where identity is not configured.
 */
export default function Identity() {
  const { t } = useTranslation();
  const me = useMe();
  const { pathname, search } = useLocation();
  const signOut = useSignOut();
  if (!me.data?.sso_configured) return null;
  if (!me.data.user) {
    return (
      <a href={signInUrl(`${pathname}${search}`)} className={linkClass} data-testid="sign-in">
        {t("auth.signIn")}
      </a>
    );
  }
  return (
    <span className="flex items-center gap-1.5">
      <span className="hidden max-w-[160px] truncate text-[12px] text-ink-2 sm:inline" title={me.data.user.email ?? undefined} data-testid="signed-in-name">
        {me.data.user.name}
      </span>
      <button type="button" onClick={() => signOut.mutate()} disabled={signOut.isPending} className={linkClass} aria-label={`${t("auth.signOut")} (${me.data.user.name})`} title={t("auth.signOut")}>
        {/* Phones get the icon only: with two language pickers beside it, the word does not fit in 360px. */}
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 sm:hidden" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 17l5-5-5-5M15 12H3M21 3v18" />
        </svg>
        <span className="hidden sm:inline">{t("auth.signOut")}</span>
      </button>
    </span>
  );
}
