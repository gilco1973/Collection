import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import type { ChatMode } from "../api/chatTypes";
import { openChat } from "../chatBus";
import { btn } from "./States";

export const MIN_SELECTION = 12;
export const MAX_SELECTION = 2000; // the API's `context.selection` limit
const SETTLE_MS = 150; // a drag (or a touch handle) fires selectionchange per move: show once it settles
const GAP = 8;
const HEIGHT = 40;
const FALLBACK_WIDTH = 240; // until the toolbar has been measured
const ACTIONS: { mode: ChatMode; label: string }[] = [
  { mode: "explain", label: "quiz.explain" },
  { mode: "elaborate", label: "quiz.elaborate" },
  { mode: "quiz", label: "quiz.quizMe" },
];

interface Anchor {
  text: string;
  top: number;
  bottom: number;
  left: number;
  width: number;
}

/** The current selection as a usable passage inside `container` (viewport coordinates), else null. */
function readSelection(container: HTMLElement | null): Anchor | null {
  const selection = window.getSelection?.();
  if (!container || !selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const text = selection.toString().trim();
  if (text.length < MIN_SELECTION || text.length > MAX_SELECTION) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;
  const rect = range.getBoundingClientRect();
  return { text, top: rect.top, bottom: rect.bottom, left: rect.left, width: rect.width };
}

const same = (a: Anchor | null, b: Anchor | null) =>
  a === b || (!!a && !!b && a.text === b.text && a.top === b.top && a.bottom === b.bottom && a.left === b.left && a.width === b.width);
const clearSelection = () => window.getSelection?.()?.removeAllRanges();

interface Props {
  articleRef: RefObject<HTMLElement>;
  path: string;
  title: string;
}

/**
 * A small floating toolbar over text the reader selected in the article: Explain / Elaborate /
 * Quiz me hand the passage (with the page) to the chat widget through the chat bus.
 */
export default function SelectionToolbar({ articleRef, path, title }: Props) {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const anchorRef = useRef(anchor);
  anchorRef.current = anchor;
  const toolbarRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  useLayoutEffect(() => {
    // Measured once the toolbar is in the DOM (labels differ per locale), so the clamp below uses the
    // real width, not a guess; re-measured whenever it is shown for a new selection.
    const measured = toolbarRef.current?.offsetWidth;
    if (measured) setWidth((current) => (measured === current ? current : measured));
  }, [anchor]);

  useEffect(() => {
    let timer: number | undefined;
    const place = (next: Anchor | null) => setAnchor((prev) => (same(prev, next) ? prev : next));
    const show = () => {
      window.clearTimeout(timer);
      place(readSelection(articleRef.current));
    };
    const onSelectionChange = () => {
      window.clearTimeout(timer);
      if (!readSelection(articleRef.current)) return place(null); // gone: hide at once
      timer = window.setTimeout(show, SETTLE_MS);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return show();
      if (anchorRef.current) clearSelection(); // only a selection the toolbar is up for; never someone else's
      place(null);
    };
    document.addEventListener("selectionchange", onSelectionChange);
    document.addEventListener("mouseup", show);
    document.addEventListener("keyup", onKeyUp);
    window.addEventListener("scroll", show, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("selectionchange", onSelectionChange);
      document.removeEventListener("mouseup", show);
      document.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("scroll", show, true);
    };
  }, [articleRef]);

  if (!anchor) return null;
  const left = Math.min(Math.max(GAP, anchor.left + anchor.width / 2 - width / 2), Math.max(GAP, window.innerWidth - width - GAP));
  const top = anchor.top - HEIGHT - GAP >= GAP ? anchor.top - HEIGHT - GAP : anchor.bottom + GAP;
  const choose = (mode: ChatMode) => {
    openChat({ mode, context: { path, title, selection: anchor.text } });
    clearSelection();
    setAnchor(null);
  };
  return (
    <div ref={toolbarRef} role="toolbar" aria-label={t("quiz.toolbarLabel")} style={{ top, left }} className="motion-safe:animate-scale-in fixed z-50 flex max-w-[calc(100vw-16px)] flex-wrap items-center gap-1 rounded-s border border-rule bg-surface p-1 shadow-2">
      {ACTIONS.map((action) => (
        <button key={action.mode} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(action.mode)} className={btn}>
          {t(action.label)}
        </button>
      ))}
    </div>
  );
}
