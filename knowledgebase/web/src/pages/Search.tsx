import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { useSearch } from "../api/hooks";
import { StatusBadge } from "../components/Badges";
import { Empty, ErrorBox, Loading } from "../components/States";
import VoiceInputButton from "../components/VoiceInputButton";
import { useContentLanguage } from "../contentLanguage";
import { usePageTitle } from "../usePageTitle";

const FILTERS = ["section", "status", "audience", "owner"] as const;
const DEBOUNCE_MS = 300;
const select = "h-[34px] rounded-s border border-rule-2 bg-surface px-2 text-[13px] text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export default function Search() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const contentLang = useContentLanguage();
  usePageTitle(t("search.title"));
  const values = Object.fromEntries(FILTERS.map((f) => [f, params.get(f) ?? undefined]));
  const q = params.get("q") ?? "";
  const stale = params.get("stale") ?? undefined;
  const [text, setText] = useState(q);
  const result = useSearch({ q, stale, lang: contentLang, ...values });
  // The debounce timer holds an old closure and react-router recreates setSearchParams per render,
  // so both the params and the setter are read through refs: a filter chosen inside the window survives.
  const latest = useRef({ params, setParams });
  latest.current = { params, setParams };
  const update = (key: string, value: string, replace = false) => {
    const next = new URLSearchParams(latest.current.params);
    if (value) next.set(key, value);
    else next.delete(key);
    latest.current.setParams(next, { replace });
  };
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    if (text === q) return;
    const handle = setTimeout(() => update("q", text, true), DEBOUNCE_MS); // typing replaces history
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{t("search.title")}</h1>
      <label className="flex h-[52px] max-w-[760px] items-center gap-3 rounded-[10px] border border-rule-2 bg-surface px-4 shadow-1 focus-within:ring-2 focus-within:ring-accent">
        <span className="sr-only">{t("search.title")}</span>
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input type="search" placeholder={t("search.placeholder")} value={text} onChange={(e) => setText(e.target.value)}
          className="h-full w-full bg-transparent text-[15px] text-ink placeholder:text-faint focus:outline-none" />
        <VoiceInputButton onResult={setText} />
      </label>
      <fieldset className="flex flex-wrap items-end gap-3 text-[12px] font-medium text-muted">
        <legend className="sr-only">{t("search.filters")}</legend>
        {FILTERS.map((f) => {
          const options = result.data?.facets[f] ?? [];
          const selected = values[f];
          return (
            <label key={f} className="flex flex-col gap-1">{t(`search.${f}`)}
              <select className={select} value={selected ?? ""} onChange={(e) => update(f, e.target.value)}>
                <option value="">{t("search.any")}</option>
                {selected && !options.some((o) => o.value === selected) && <option value={selected}>{selected}</option>}
                {options.map((o) => <option key={o.value} value={o.value}>{o.value} ({o.count})</option>)}
              </select>
            </label>
          );
        })}
        <label className="flex h-[34px] items-center gap-2 text-ink-2"><input type="checkbox" className="accent-accent" checked={stale === "true"} onChange={(e) => update("stale", e.target.checked ? "true" : "")} />{t("search.staleOnly")}</label>
      </fieldset>
      {result.isPending ? <Loading /> : result.error ? <ErrorBox error={result.error} onRetry={() => result.refetch()} /> : !result.data.total ? (
        <Empty text={t("search.noResults")} />
      ) : (
        <div className="rounded border border-rule bg-surface shadow-1">
          <p role="status" className="border-b border-rule px-4 py-2 text-[12px] font-medium text-muted">{t("search.results", { count: result.data.total })}</p>
          <ul aria-busy={result.isPlaceholderData} className={`divide-y divide-rule ${result.isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}`}>
            {result.data.items.map((p, i) => (
              <li key={p.path} className="motion-safe:animate-rise flex flex-col gap-1 px-4 py-3" style={{ animationDelay: `${Math.min(i * 20, 200)}ms` }}>
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/kb/page/${p.path}`} className="break-words text-[13.5px] font-semibold text-ink hover:text-accent hover:underline">{p.title}</Link>
                  <StatusBadge status={p.status} />
                </div>
                {p.snippet && <p className="max-w-[80ch] text-[13px] text-ink-2">{p.snippet}</p>}
                <p className="font-mono text-[11px] text-faint"><bdi>{p.section}</bdi> · <bdi>{p.owner}</bdi></p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
