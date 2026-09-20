import { useId, useRef } from "react";

export interface TabSpec<K extends string> { key: K; label: string }

interface Props<K extends string> {
  tabs: TabSpec<K>[];
  current: K;
  label: string;
  onChange: (key: K) => void;
  children: React.ReactNode;
}

/** WAI-ARIA tabs: roving tabindex, arrow/Home/End keys (mirrored in RTL), automatic activation, labelled panel. */
export default function Tabs<K extends string>({ tabs, current, label, onChange, children }: Props<K>) {
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const idx = Math.max(0, tabs.findIndex((t) => t.key === current));
  const move = (to: number) => {
    const next = tabs[(to + tabs.length) % tabs.length];
    onChange(next.key);
    refs.current[next.key]?.focus();
  };
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const rtl = getComputedStyle(e.currentTarget).direction === "rtl";
    const forward = rtl ? "ArrowLeft" : "ArrowRight";
    const backward = rtl ? "ArrowRight" : "ArrowLeft";
    const keys: Record<string, () => void> = {
      [forward]: () => move(idx + 1),
      [backward]: () => move(idx - 1),
      Home: () => move(0),
      End: () => move(tabs.length - 1),
    };
    const handler = keys[e.key];
    if (handler) { e.preventDefault(); handler(); }
  };
  return (
    <>
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex flex-wrap gap-0.5 border-b border-rule">
        {tabs.map((tab) => {
          const selected = tab.key === current;
          return (
            <button key={tab.key} ref={(el) => { refs.current[tab.key] = el; }} type="button" role="tab" id={`${base}-tab-${tab.key}`}
              aria-selected={selected} aria-controls={`${base}-panel`} tabIndex={selected ? 0 : -1} onClick={() => onChange(tab.key)}
              className={`-mb-px flex min-h-11 items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${selected ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}>
              {tab.label}
            </button>
          );
        })}
      </div>
      <div key={current} role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-tab-${current}`} tabIndex={0}
        className="motion-safe:animate-fade-in rounded outline-none focus-visible:ring-2 focus-visible:ring-accent">
        {children}
      </div>
    </>
  );
}
