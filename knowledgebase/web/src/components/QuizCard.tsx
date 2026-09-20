import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { QuizQuestion } from "../api/chatTypes";
import { useRecordQuiz, useSignedIn } from "../api/hooks";
import { btn, btnPrimary } from "./States";

/** The reader's picks (one index per question) and whether they have checked them. */
export interface QuizState {
  picked: (number | undefined)[];
  checked: boolean;
}

interface Props {
  questions: QuizQuestion[];
  path: string;
  /** Owned by the message the quiz belongs to, so the card can unmount (panel closed) and come back as it was. */
  state?: QuizState;
  onState: (next: QuizState) => void;
  /** Send a plain question back to the librarian (used for "explain what I got wrong"). */
  onAsk: (message: string) => void;
}

const MAX_MESSAGE = 2000; // the API's `message` limit

/**
 * A multiple-choice quiz graded in the browser: the answers never leave it. Only the tally
 * (`{path, score, total}`) is recorded, once, and only for a signed-in reader.
 */
export default function QuizCard({ questions, path, state, onState, onAsk }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const picked = state?.picked ?? questions.map(() => undefined);
  const checked = state?.checked ?? false;
  const signedIn = useSignedIn();
  const record = useRecordQuiz();
  const score = questions.filter((q, i) => picked[i] === q.answer).length;
  const missed = questions.map((q, i) => ({ q, i })).filter(({ q, i }) => picked[i] !== q.answer);
  const scoreRef = useRef<HTMLParagraphElement>(null);
  const justChecked = useRef(false);
  useEffect(() => {
    // "Check answers" unmounts itself; land the keyboard on the score line instead of on <body>.
    if (checked && justChecked.current) scoreRef.current?.focus();
    justChecked.current = false;
  }, [checked]);

  const pick = (i: number, j: number) => onState({ picked: picked.map((p, k) => (k === i ? j : p)), checked });
  const check = () => {
    justChecked.current = true;
    onState({ picked, checked: true });
    if (signedIn && path) record.mutate({ path, score, total: questions.length });
  };
  const explainMistakes = () => {
    const lines = missed.map(({ q, i }, n) => t("quiz.missedLine", { n: n + 1, question: q.q, chosen: q.options[picked[i] ?? -1] ?? "—", answer: q.options[q.answer] }));
    onAsk([t("quiz.explainMistakesPrompt"), ...lines].join("\n").slice(0, MAX_MESSAGE));
  };

  return (
    <div className="flex flex-col gap-3">
      {questions.map((q, i) => {
        const right = checked && picked[i] === q.answer;
        return (
          <fieldset key={i} className="flex flex-col gap-1">
            <legend className="mb-1 font-medium">{`${i + 1}. ${q.q}`}</legend>
            {q.options.map((option, j) => {
              const tone = checked && j === q.answer ? "bg-ok-soft text-ok" : checked && picked[i] === j ? "bg-crit-soft text-crit" : "hover:bg-surface-3";
              return (
                <label key={j} className={`flex cursor-pointer items-start gap-2 rounded-s px-2 py-1 ${tone}`}>
                  <input type="radio" name={`${id}-${i}`} checked={picked[i] === j} disabled={checked} onChange={() => pick(i, j)} className="mt-0.5" />
                  <span>{option}</span>
                </label>
              );
            })}
            {checked && (
              <p className={`px-2 text-[12px] ${right ? "text-ok" : "text-crit"}`}>
                <span className="font-semibold">{right ? `✓ ${t("quiz.correct")}` : `✗ ${t("quiz.incorrect")}`}</span>
                {q.why && <span className="text-muted">{` — ${q.why}`}</span>}
              </p>
            )}
          </fieldset>
        );
      })}
      {checked ? (
        <div className="flex flex-col gap-2">
          <p ref={scoreRef} tabIndex={-1} role="status" className="rounded font-medium outline-none focus-visible:ring-2 focus-visible:ring-accent">{t("quiz.score", { score, total: questions.length })}</p>
          {record.isSuccess && <p className="text-[12px] text-muted">{t("quiz.recorded")}</p>}
          {record.error && <p className="text-[12px] text-crit">{record.error.message}</p>}
          {missed.length > 0 && (
            <div><button type="button" onClick={explainMistakes} className={btn}>{t("quiz.explainMistakes")}</button></div>
          )}
        </div>
      ) : (
        <div><button type="button" onClick={check} disabled={picked.some((p) => p === undefined)} className={btnPrimary}>{t("quiz.check")}</button></div>
      )}
    </div>
  );
}
