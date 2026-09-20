import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReviewItem, Severity, ToolCall } from "../api/types";
import { formatDate } from "../format";
import { SeverityBadge } from "./Badges";
import { Empty } from "./States";

const SEVERITIES: readonly string[] = ["critical", "error", "warning", "info"];

export function ReviewQueue({ items }: { items: ReviewItem[] }) {
  const { t, i18n } = useTranslation();
  if (!items.length) return <Empty text={t("audit.noReview")} />;
  return (
    <ul className="divide-y divide-rule">
      {items.map((it, n) => (
        <li key={`${it.path}-${it.at}-${n}`} className="py-2 text-sm">
          <Link to={`/kb/page/${it.path}`} dir="ltr" className="break-all font-mono text-accent underline">{it.path}</Link>
          <span className="ms-2">
            {SEVERITIES.includes(it.severity) ? <SeverityBadge severity={it.severity as Severity} /> : <span className="text-xs uppercase text-muted">{it.severity}</span>}
          </span>
          <span className="ms-2 text-xs text-muted">{formatDate(it.at, i18n.language)}</span>
          <p>{it.reason}</p>
        </li>
      ))}
    </ul>
  );
}

export function ToolTrail({ calls }: { calls: ToolCall[] }) {
  const { t, i18n } = useTranslation();
  if (!calls.length) return <Empty text={t("audit.noTrail")} />;
  return (
    <ol className="divide-y divide-rule text-sm">
      {calls.map((c, n) => (
        <li key={`${c.at}-${c.tool}-${n}`} className="py-2">
          <span className={`me-2 rounded px-1.5 py-0.5 text-xs font-semibold ${c.ok ? "bg-ok-soft" : "bg-crit-soft"}`}>
            {c.ok ? t("audit.ok") : c.summary.startsWith("denied") ? t("audit.denied") : t("audit.failed")}
          </span>
          <span className="font-mono">{c.tool}</span>
          <span className="ms-2 text-xs text-muted">{formatDate(c.at, i18n.language)}</span>
          <p className="text-xs text-muted">{c.summary}</p>
          {Object.keys(c.input).length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-muted">{t("audit.input")}</summary>
              <pre dir="ltr" className="mt-1 overflow-x-auto rounded bg-surface-3 p-2 font-mono text-xs">{JSON.stringify(c.input, null, 1)}</pre>
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}
