import { useEffect, useState } from "react";
import { Close, Sparkle } from "../../ui/icons";
import { useGuide } from "./GuideProvider";

/**
 * The floating button that opens the guide, and the one-line "peek" it shows
 * when a fresh next step is waiting on this page. The peek shows once per
 * nudge and goes quiet on its own; the badge stays until the person looks.
 */
export function GuideLauncher() {
  const g = useGuide();
  const [peek, setPeek] = useState<string | undefined>();
  const [seen, setSeen] = useState<string[]>([]);
  const nudgeId = g.nudge?.id;

  useEffect(() => {
    if (!nudgeId || g.isOpen || seen.includes(nudgeId)) return;
    const show = window.setTimeout(() => setPeek(nudgeId), 1200);
    const hide = window.setTimeout(() => setPeek(undefined), 12_000);
    setSeen((s) => [...s, nudgeId]);
    return () => {
      window.clearTimeout(show);
      window.clearTimeout(hide);
    };
    // A nudge peeks once; `seen` is the record of that, not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nudgeId, g.isOpen]);

  useEffect(() => {
    document.body.setAttribute("data-guide-on", "");
    return () => document.body.removeAttribute("data-guide-on");
  }, []);

  const pending = g.nudge && !g.isOpen ? 1 : 0;
  const peeking = peek && g.nudge && peek === g.nudge.id && !g.isOpen;

  return (
    <div className="guide-launcher">
      {peeking && (
        <div className="guide-peek" role="status">
          <button type="button" className="guide-peek-body" onClick={() => g.open()}>
            <span className="guide-peek-kicker">Next step</span>
            <span>{g.nudge!.text}</span>
          </button>
          <button
            type="button"
            className="guide-peek-x"
            aria-label="Not now"
            onClick={() => {
              setPeek(undefined);
              g.dismiss(g.nudge!.id);
            }}
          >
            <Close size={12} />
          </button>
        </div>
      )}
      <button
        type="button"
        className={`guide-fab${g.isOpen ? " on" : ""}`}
        aria-label={g.isOpen ? "Close the guide" : "Open the guide"}
        aria-expanded={g.isOpen}
        aria-controls="hub-guide"
        title="Guide (Alt+G)"
        onClick={() => g.toggle()}
      >
        {g.isOpen ? <Close size={18} /> : <Sparkle size={18} />}
        {pending > 0 && <span className="guide-badge" aria-label="A next step is waiting" />}
      </button>
    </div>
  );
}
