import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ArrowLeft, ArrowRight } from "../../ui/icons";
import { TOURS } from "./model";

/**
 * A spotlight tour: navigate to a page, find the element marked
 * `data-guide="<target>"`, dim everything else and put a callout beside it.
 * Nothing on the page is changed; the spotlight is drawn over it and follows
 * scroll and resize. Escape or "Done" ends it; the person keeps the page.
 */
interface Props {
  id: string;
  step: number;
  onNext: () => void;
  onBack: () => void;
  onEnd: () => void;
  navigate: (route: string) => void;
}

type Rect = { top: number; left: number; width: number; height: number };
const PAD = 8;

export function Tour({ id, step, onNext, onBack, onEnd, navigate }: Props) {
  const tour = TOURS[id];
  const s = tour?.steps[step];
  const location = useLocation();
  const [rect, setRect] = useState<Rect | undefined>();
  const [missing, setMissing] = useState(false);
  const calloutRef = useRef<HTMLDivElement>(null);
  const targetRef = useRef<Element | null>(null);

  // Go where the step lives.
  useEffect(() => {
    if (s && location.pathname !== s.route) navigate(s.route);
    // Only when the step changes; the route settles on its own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s?.route, step]);

  // Find the target once the page has rendered it (data may still be loading), then track it.
  useLayoutEffect(() => {
    if (!s) return;
    let tries = 0;
    let raf = 0;
    let timer = 0;
    setRect(undefined);
    setMissing(false);
    const measure = () => {
      const el = targetRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 });
    };
    const find = () => {
      const el = document.querySelector(`[data-guide="${s.target}"]`);
      if (el) {
        targetRef.current = el;
        el.scrollIntoView({ block: "center", behavior: "auto" });
        raf = requestAnimationFrame(() => {
          measure();
          calloutRef.current?.focus();
        });
        return;
      }
      if (++tries < 40) timer = window.setTimeout(find, 100);
      else setMissing(true);
    };
    find();
    const onMove = () => measure();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
      targetRef.current = null;
    };
  }, [s, location.pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onEnd();
      if (e.key === "ArrowRight") onNext();
      if (e.key === "ArrowLeft") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onEnd, onNext, onBack]);

  if (!tour || !s) return null;
  const last = step === tour.steps.length - 1;

  // The callout sits under the target when there is room, above it otherwise; clamped to the viewport.
  const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const calloutW = Math.min(380, vw - 32);
  let top = 96;
  let left = Math.max(16, (vw - calloutW) / 2);
  let arrow: "up" | "down" | "none" = "none";
  if (rect) {
    const below = rect.top + rect.height + 12;
    if (below + 180 < vh) {
      top = below;
      arrow = "up";
    } else {
      top = Math.max(16, rect.top - 12 - 180);
      arrow = "down";
    }
    left = Math.min(Math.max(16, rect.left), vw - calloutW - 16);
  }

  return (
    <div className="guide-tour" role="presentation">
      {rect ? (
        <div className="guide-spot" style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }} aria-hidden="true" />
      ) : (
        <div className="guide-scrim" aria-hidden="true" />
      )}
      <div
        ref={calloutRef}
        className={`guide-callout arrow-${arrow}`}
        role="dialog"
        aria-label={`Tour: ${tour.title}, step ${step + 1} of ${tour.steps.length}`}
        tabIndex={-1}
        style={{ top, left, width: calloutW }}
      >
        <div className="guide-kicker">
          {tour.title} · {step + 1} of {tour.steps.length}
        </div>
        <h3>{s.title}</h3>
        <p className="guide-p">{s.body}</p>
        {missing && <p className="guide-p muted">This part is not on the page right now; carry on to the next step.</p>}
        <div className="row" style={{ gap: 8, marginTop: 4 }}>
          <button type="button" className="btn g s" onClick={onBack} disabled={step === 0}>
            <ArrowLeft size={12} />
            Back
          </button>
          <span className="sp" />
          <button type="button" className="btn g s" onClick={onEnd}>
            {last ? "Close" : "Stop the tour"}
          </button>
          <button type="button" className="btn p s" onClick={last ? onEnd : onNext} data-autofocus>
            {last ? "Done" : "Next"}
            {!last && <ArrowRight size={12} />}
          </button>
        </div>
      </div>
    </div>
  );
}
