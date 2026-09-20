import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";

/** Hub button styles: 32px tall, 13px semibold. */
export const btn = "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-s border border-rule-2 bg-surface px-3 text-[13px] font-semibold text-ink shadow-1 transition hover:bg-surface-2 active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:active:scale-100 disabled:opacity-50";
export const btnPrimary = "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-s border border-ink bg-ink px-3 text-[13px] font-semibold text-bg shadow-1 transition hover:bg-ink-2 hover:border-ink-2 active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:active:scale-100 disabled:opacity-50";
export const btnDanger = "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-s border border-crit bg-crit px-3 text-[13px] font-semibold text-on-crit shadow-1 transition active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:active:scale-100 disabled:opacity-50";
export const input = "h-[34px] w-full rounded-s border border-rule-2 bg-surface px-2.5 text-[13px] text-ink placeholder:text-faint transition-shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-accent";
export const label = "block text-[12px] font-medium text-muted";

export function Loading() {
  const { t } = useTranslation();
  return (
    <p role="status" className="flex items-center justify-center gap-2 py-8 text-center text-muted">
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 animate-spin text-faint">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeDasharray="42" strokeDashoffset="30" strokeLinecap="round" />
      </svg>
      {t("common.loading")}
    </p>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const message = error instanceof Error ? error.message : t("common.error");
  const requestId = error instanceof ApiError ? error.requestId : undefined;
  return (
    <div role="alert" className="rounded border border-crit/30 bg-crit-soft p-4 text-crit">
      <p className="font-medium">{message}</p>
      {requestId && <p className="font-mono text-[11px]">{t("common.requestId", { id: requestId })}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className={`${btnDanger} mt-2`}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function Empty({ text }: { text?: string }) {
  const { t } = useTranslation();
  return <p className="motion-safe:animate-fade-in py-8 text-center text-muted">{text ?? t("common.empty")}</p>;
}

/** Hub section: a heading row (title + muted subtitle + actions) above a card. */
export function Card({ title, sub, children, actions, className = "" }: { title?: string; sub?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <section className={`motion-safe:animate-rise flex min-w-0 flex-col gap-3 ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <div className="flex items-baseline gap-3">
            {title && <h2 className="text-[17px] font-semibold tracking-[-0.01em]">{title}</h2>}
            {sub && <span className="text-[13px] text-muted">{sub}</span>}
          </div>
          {actions}
        </header>
      )}
      <div className="rounded border border-rule bg-surface p-4 shadow-1">{children}</div>
    </section>
  );
}
