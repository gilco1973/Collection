import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { btn, input } from "./States";

interface Props {
  title: string;
  description: string;
  token: string;
  confirmLabel: string;
  busy?: boolean;
  extra?: React.ReactNode;
  /** Render in the page flow instead of as an overlay (used when the confirmation is the page). */
  inline?: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/** Modal confirmation: focus moves to the reason, Tab is trapped, Escape cancels, focus is restored on close. */
export default function ConfirmWithReason({ title, description, token, confirmLabel, busy, extra, inline, onConfirm, onCancel }: Props) {
  const { t } = useTranslation();
  const ids = { title: useId(), desc: useId(), help: useId() };
  const box = useRef<HTMLDivElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const ready = typed === token && reason.trim().length >= 10 && !busy;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const bodyOverflow = document.body.style.overflow;
    if (!inline) document.body.style.overflow = "hidden"; // the page behind an overlay must not scroll
    reasonRef.current?.focus();
    return () => {
      document.body.style.overflow = bodyOverflow;
      previous?.focus?.();
    };
  }, [inline]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (inline) return; // in the page flow, Escape must not discard a half-typed reason
    if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key !== "Tab" || !box.current) return;
    const nodes = Array.from(box.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (!nodes.length) return;
    const [head, tail] = [nodes[0], nodes[nodes.length - 1]];
    if (e.shiftKey && document.activeElement === head) { e.preventDefault(); tail.focus(); }
    else if (!e.shiftKey && document.activeElement === tail) { e.preventDefault(); head.focus(); }
  };

  const dialog = (
    <div ref={box} role="alertdialog" aria-modal={!inline} aria-labelledby={ids.title} aria-describedby={ids.desc} onKeyDown={onKeyDown}
      className="motion-safe:animate-scale-in w-full max-w-lg rounded-l border border-warn bg-surface p-5 shadow-3">
      <h2 id={ids.title} className="text-[17px] font-semibold tracking-[-0.01em]">{title}</h2>
      <p id={ids.desc} className="mt-1 text-sm">{description}</p>
      <label className="mt-3 block text-[12px] font-medium text-muted">
        {t("common.reason")}
        <textarea ref={reasonRef} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} aria-describedby={ids.help}
          className={`${input} mt-1 h-auto min-h-[72px] py-2`} />
      </label>
      <p id={ids.help} className="mt-1 text-[12px] text-muted">{t("common.reasonHelp")}</p>
      {extra}
      <label className="mt-3 block text-[12px] font-medium text-muted">
        {t("common.typeToConfirm", { token })}
        <input value={typed} onChange={(e) => setTyped(e.target.value)} dir="ltr" autoComplete="off" spellCheck={false}
          className={`${input} mt-1 font-mono`} />
      </label>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className={btn}>
          {t("common.cancel")}
        </button>
        <button type="button" disabled={!ready} onClick={() => onConfirm(reason.trim())}
          className={`${btn} border-warn bg-warn text-on-warn hover:bg-warn`}>
          {confirmLabel}
        </button>
      </div>
    </div>
  );
  if (inline) return dialog;
  return <div className="motion-safe:animate-fade-in fixed inset-0 z-40 flex max-h-[100dvh] items-center justify-center overflow-y-auto bg-black/50 p-4">{dialog}</div>;
}
