import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

/**
 * Notifications. One region, `aria-live="polite"`, so screen readers announce
 * a result ("Brief filed") without stealing focus. Errors use `assertive`.
 */
export type ToastKind = "ok" | "warn" | "crit" | "accent";
export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
  detail?: string;
}

interface Api {
  notify(kind: ToastKind, text: string, detail?: string): void;
  dismiss(id: number): void;
  toasts: Toast[];
}

const Ctx = createContext<Api | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const notify = useCallback(
    (kind: ToastKind, text: string, detail?: string) => {
      const id = ++seq.current;
      setToasts((t) => [...t, { id, kind, text, detail }]);
      window.setTimeout(() => dismiss(id), kind === "crit" ? 9000 : 5000);
    },
    [dismiss],
  );
  const api = useMemo(() => ({ notify, dismiss, toasts }), [notify, dismiss, toasts]);
  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toasts" aria-live="polite" aria-relevant="additions">
        {toasts.map((t) => (
          <div key={t.id} className={`banner ${t.kind}`} role={t.kind === "crit" ? "alert" : "status"}>
            <div className="col" style={{ gap: 2, flex: 1 }}>
              <b>{t.text}</b>
              {t.detail && <span style={{ fontSize: 12 }}>{t.detail}</span>}
            </div>
            <button type="button" className="btn g s" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              ×
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): Api {
  const api = useContext(Ctx);
  if (!api) throw new Error("useToast outside ToastProvider");
  return api;
}
