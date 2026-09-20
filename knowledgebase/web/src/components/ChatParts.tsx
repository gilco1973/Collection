import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ChatContext, QuizQuestion } from "../api/chatTypes";
import type { ChatSource } from "../api/types";
import QuizCard, { type QuizState } from "./QuizCard";
import TypewriterText from "./TypewriterText";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
  error?: boolean;
  animated?: boolean; // the typewriter reveal plays once, then the message renders as plain text
  quiz?: QuizQuestion[]; // a `quiz` answer: rendered as a QuizCard, and `content` is empty
  quizState?: QuizState; // the reader's picks and whether they checked: kept here so closing the panel loses nothing
  context?: ChatContext; // the page (and passage) the turn was about
}

const EXCERPT = 90;
const excerpt = (text: string, max = EXCERPT): string => (text.length > max ? `${text.slice(0, max).trimEnd()}…` : text);

/** The page (and selected passage) the next question is about, with a control to drop it. */
export function ContextChip({ context, onClear }: { context: ChatContext; onClear: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-start gap-2 border-t border-rule bg-surface-2 px-4 py-2 text-[12px]">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{t("quiz.about", { title: context.title })}</p>
        {context.selection && <p className="truncate italic text-muted">“{excerpt(context.selection)}”</p>}
      </div>
      <button type="button" onClick={onClear} aria-label={t("quiz.clearContext")} className="rounded-s p-1 text-muted hover:bg-surface-3 hover:text-ink">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </div>
  );
}

interface BubbleProps {
  m: Message;
  onPatch: (patch: Partial<Message>) => void;
  onAsk: (message: string, context?: ChatContext) => void;
  onNavigate: () => void;
}

/** One turn: the reader's question (with the passage it was about) or the librarian's answer, quiz or error. */
export function MessageBubble({ m, onPatch, onAsk, onNavigate }: BubbleProps) {
  const user = m.role === "user";
  const tone = user ? "bg-emphasis text-on-emphasis" : m.error ? "bg-crit-soft text-crit" : "bg-surface-2 text-ink";
  return (
    <div className={`flex flex-col gap-1.5 ${user ? "items-end" : "items-start"}`}>
      <div className={`${m.quiz ? "w-full" : "max-w-[85%]"} rounded px-3 py-2 text-[13px] leading-[1.5] ${tone}`}>
        {m.quiz ? (
          <QuizCard questions={m.quiz} path={m.context?.path ?? ""} state={m.quizState} onState={(quizState) => onPatch({ quizState })} onAsk={(text) => onAsk(text, m.context)} />
        ) : !user && !m.animated ? (
          <TypewriterText text={m.content} onDone={() => onPatch({ animated: true })} />
        ) : (
          m.content
        )}
      </div>
      {user && m.context?.selection && <p className="max-w-[85%] truncate text-[11px] italic text-muted">“{excerpt(m.context.selection)}”</p>}
      {!!m.sources?.length && (
        <div className="flex flex-wrap gap-1.5">
          {m.sources.map((s) => (
            <Link key={s.path} to={`/kb/page/${s.path}`} onClick={onNavigate} className="rounded-s border border-rule bg-surface px-1.5 py-0.5 text-[11px] text-accent hover:underline">
              {s.title}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
