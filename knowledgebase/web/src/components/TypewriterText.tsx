import { useEffect, useRef, useState } from "react";

const CHAR_INTERVAL_MS = 16;

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Reveals `text` character by character with a blinking caret; the reveal itself (not just the
 * caret) is skipped under prefers-reduced-motion, since it runs on a timer, not CSS. */
export default function TypewriterText({ text, onDone }: { text: string; onDone?: () => void }) {
  const reduced = useRef(prefersReducedMotion());
  const [shown, setShown] = useState(reduced.current ? text.length : 0);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    if (reduced.current) {
      setShown(text.length);
      doneRef.current?.();
      return;
    }
    setShown(0);
    if (!text) return;
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= text.length) {
        clearInterval(id);
        doneRef.current?.();
      }
    }, CHAR_INTERVAL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const finished = shown >= text.length;
  return (
    <span>
      {text.slice(0, shown)}
      {!finished && (
        <span
          aria-hidden="true"
          className="motion-safe:animate-caret-blink ms-0.5 -mb-[1px] inline-block h-[1em] w-[2px] align-middle bg-current"
        />
      )}
    </span>
  );
}
