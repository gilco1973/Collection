import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatContext, ChatMode } from "../api/chatTypes";
import { useChat } from "../api/hooks";
import { useChatRequest } from "../chatBus";
import { useContentLanguage } from "../contentLanguage";
import { ContextChip, MessageBubble, type Message } from "./ChatParts";
import VoiceInputButton from "./VoiceInputButton";

let nextId = 0;
const newId = () => `chat-${++nextId}`;
/** What the reader "says" when they press a toolbar action; the passage itself travels as context. */
const REQUEST_TEXT: Record<Exclude<ChatMode, "ask">, string> = { explain: "quiz.requestExplain", elaborate: "quiz.requestElaborate", quiz: "quiz.requestQuiz" };

export default function ChatWidget() {
  const { t } = useTranslation();
  const contentLang = useContentLanguage();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [context, setContext] = useState<ChatContext | undefined>();
  const chat = useChat();
  const request = useChatRequest();
  const opened = useRef(request?.seq ?? 0); // requests made before this widget mounted are not replayed
  const handled = useRef(request?.seq ?? 0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight; // plain scrollTop over scrollTo: works even where scrollTo doesn't exist
  }, [messages, chat.isPending]);

  const patchMessage = (id: string, patch: Partial<Message>) => setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));

  const send = (raw: string, mode: ChatMode = "ask", ctx: ChatContext | undefined = context) => {
    const question = raw.trim();
    if (!question || chat.isPending) return;
    const history = messages.filter((m) => m.content).slice(-8).map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { id: newId(), role: "user", content: question, animated: true, context: ctx }]);
    setInput("");
    chat.mutate(
      { message: question, history, lang: contentLang === "en" ? undefined : contentLang, mode: mode === "ask" ? undefined : mode, context: ctx },
      {
        onSuccess: (result) =>
          setMessages((prev) => [
            ...prev,
            { id: newId(), role: "assistant", content: result.answer, sources: result.sources, quiz: result.quiz, context: ctx, animated: !!result.quiz },
          ]),
        onError: (error) =>
          setMessages((prev) => [
            ...prev,
            { id: newId(), role: "assistant", content: error instanceof Error ? error.message : t("chat.error"), error: true },
          ]),
      },
    );
  };
  const sendRef = useRef(send);
  sendRef.current = send;
  const contextRef = useRef(context);
  contextRef.current = context;

  useEffect(() => {
    // A request from the selection toolbar or a `?quiz=1` link: open and take the page as context at once.
    // The three actions are sent as soon as no turn is in flight — queued, never dropped — with nothing to type.
    // A held action goes out with the chip as it is by then: if the reader cleared it meanwhile, it is not sent.
    if (!request || request.seq === handled.current) return;
    const fresh = request.seq !== opened.current;
    if (fresh) {
      opened.current = request.seq;
      setOpen(true);
      setContext(request.context);
    }
    if (request.mode === "ask") {
      handled.current = request.seq; // grounds the next typed question; nothing to send
      return;
    }
    if (chat.isPending) return;
    const ctx = fresh ? request.context : contextRef.current;
    handled.current = request.seq;
    if (ctx) sendRef.current(t(REQUEST_TEXT[request.mode]), request.mode, ctx);
  }, [request, t, chat.isPending]);

  return (
    <div className="fixed inset-x-4 bottom-24 z-40 flex flex-col items-end gap-3 sm:inset-x-auto sm:end-4 md:bottom-4">
      {open && (
        <div role="dialog" aria-label={t("chat.title")} className="motion-safe:animate-rise flex h-[70vh] max-h-[560px] w-full flex-col overflow-hidden rounded-l border border-rule bg-surface shadow-3 sm:w-[360px]">
          <div className="flex items-center justify-between border-b border-rule bg-surface-2 px-4 py-3">
            <span className="text-[13px] font-semibold">{t("chat.title")}</span>
            <button type="button" onClick={() => setOpen(false)} aria-label={t("chat.closeLabel")} className="rounded-s p-1 text-muted hover:bg-surface-3 hover:text-ink">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
            </button>
          </div>
          <div ref={listRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
            {messages.length === 0 && <p className="text-[13px] text-muted">{t("chat.emptyHint")}</p>}
            {messages.map((m) => (
              <MessageBubble key={m.id} m={m} onPatch={(patch) => patchMessage(m.id, patch)} onAsk={(text, ctx) => send(text, "ask", ctx)} onNavigate={() => setOpen(false)} />
            ))}
            {chat.isPending && <p role="status" className="text-[12px] text-muted">{chat.variables?.mode === "quiz" ? t("quiz.generating") : t("chat.thinking")}</p>}
          </div>
          {context && <ContextChip context={context} onClear={() => setContext(undefined)} />}
          <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex items-center gap-2 border-t border-rule p-3">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("chat.placeholder")}
              aria-label={t("chat.placeholder")}
              className="h-9 flex-1 rounded-s border border-rule-2 bg-surface px-2.5 text-[13px] text-ink placeholder:text-faint focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
            <VoiceInputButton onResult={send} />
            <button type="submit" disabled={!input.trim() || chat.isPending} aria-label={t("chat.send")} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-s border border-ink bg-ink text-bg transition active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </form>
        </div>
      )}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={t("chat.openLabel")}
          className="flex h-12 w-12 items-center justify-center rounded-l bg-ink text-surface shadow-2 transition-transform hover:-translate-y-px active:scale-95"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 5h16v10H8l-4 4V5z" />
          </svg>
        </button>
      )}
    </div>
  );
}
