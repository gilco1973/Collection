import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api";
import type { Chip, ConsumerSummary, ConversationSummary } from "../../api/types";
import { usePrincipal } from "../../auth/AuthProvider";
import { ROUTES } from "../../routes";
import { HubFoot, HubNav } from "../../ui/HubChrome";
import { Person, Plus, Question, Send, Sparkle } from "../../ui/icons";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useToast } from "../../ui/Toast";
import { useTitle } from "../../ui/useTitle";
import { Aside, Message, sourcesFor } from "./Views";
import { useConversation } from "./useConversation";

const DEFAULT_ASSISTANT = "employee-assistant";

/** The employee assistant and the agents this person may talk to, on one screen. */
export default function Assistant() {
  const p = usePrincipal();
  const navigate = useNavigate();
  const palette = usePalette();
  const toast = useToast();
  const { consumerId } = useParams<{ consumerId?: string }>();
  const [params] = useSearchParams();
  const playground = params.get("playground") === "1";

  const catalog = useQuery({ queryKey: ["catalog"], queryFn: ({ signal }) => api.catalog.get(signal) });
  const list = useQuery({ queryKey: ["conversations"], queryFn: ({ signal }) => api.conversations.list(signal) });

  // Assistants this person may talk to: assistants and agents the platform opened to them.
  const assistants = useMemo<ConsumerSummary[]>(
    () => (catalog.data?.listings ?? []).filter((l) => (l.kind === "assistant" || l.kind === "agent") && l.access === "open" && p.entitlements.includes(l.id)),
    [catalog.data, p.entitlements],
  );
  const assistantId = consumerId && assistants.some((a) => a.id === consumerId) ? consumerId : DEFAULT_ASSISTANT;
  const activeListing = assistants.find((a) => a.id === assistantId);

  // Which conversation: chosen, else the latest for this assistant, else none (a new one starts on first send).
  const [chosen, setChosen] = useState<string | undefined>();
  const [fresh, setFresh] = useState(false);
  const conversationId = useMemo(() => {
    if (fresh) return undefined;
    if (chosen && list.data?.some((c) => c.id === chosen)) return chosen;
    return list.data?.find((c) => c.assistantId === assistantId)?.id;
  }, [fresh, chosen, list.data, assistantId]);

  const conv = useConversation(conversationId, assistantId);
  useTitle(activeListing?.name ?? "Assistant");

  const [draft, setDraft] = useState(params.get("q") ?? "");
  const composer = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (params.get("q")) composer.current?.focus();
  }, [params]);
  useEffect(() => {
    if (scroller.current && conv.state === "streaming") scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [conv.turns, conv.state]);

  const grow = (el: HTMLTextAreaElement) => {
    el.style.height = "20px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };
  const doSend = () => {
    const text = draft;
    setDraft("");
    if (composer.current) composer.current.style.height = "20px";
    void conv.send(text, (c) => {
      setFresh(false);
      setChosen(c.id);
    });
  };

  if (catalog.isPending || list.isPending) return <PageState kind="loading" text="Opening the assistant…" />;
  if (catalog.error || list.error)
    return <PageState kind="error" text="The assistant could not be opened." detail={((catalog.error ?? list.error) as Error).message} />;
  if (consumerId && !assistants.some((a) => a.id === consumerId)) {
    return (
      <PageState
        kind="error"
        text="That assistant is not open to your role."
        detail="Ask for access from its listing; the platform lead confirms within two working days."
        action={
          <button type="button" className="btn s" onClick={() => navigate(ROUTES.discover)}>
            Back to Discover
          </button>
        }
      />
    );
  }

  const header = conv.conversation?.assistant ?? {
    name: activeListing?.name ?? "Assistant",
    sub: activeListing?.description ?? "",
    chips: (activeListing?.meta ?? []).slice(0, 2) as Chip[],
  };
  const lastAssistant = [...conv.turns].reverse().find((t) => t.role === "assistant");
  const feedbackView = lastAssistant?.views.find((v): v is Extract<typeof v, { kind: "feedback" }> => v.kind === "feedback");
  const busy = conv.state === "streaming" || conv.state === "sending";
  const conversations: ConversationSummary[] = list.data ?? [];

  return (
    <div className="hub" data-live data-loading={conv.loading ? "true" : undefined} style={{ minHeight: "900px" }}>
      <HubNav active="My workspace" onSearch={palette.open} />
      <div className="hwrap">
        <div style={{ display: "grid", gridTemplateColumns: "260px minmax(0,1fr)", gap: "20px", minHeight: "0", gridTemplateRows: "700px" }}>
          {/* Conversations and the assistant picker */}
          <div className="card" style={{ minHeight: "0" }}>
            <div className="ch">
              <h3>Conversations</h3>
              <span className="sp"></span>
              <button
                type="button"
                className="ibtn"
                style={{ width: "28px", height: "28px" }}
                aria-label="New conversation"
                onClick={() => {
                  setFresh(true);
                  setChosen(undefined);
                  composer.current?.focus();
                }}
              >
                <Plus size={14} />
              </button>
            </div>
            <div className="cb" style={{ gap: "2px", padding: "8px", overflowY: "auto" }}>
              {conversations.map((c) => {
                const sel = c.id === conversationId;
                return (
                  <button
                    key={c.id}
                    type="button"
                    className="col conv"
                    aria-current={sel ? "true" : undefined}
                    style={{ padding: "9px 10px", borderRadius: "6px", gap: "1px", background: sel ? "var(--surface-3)" : undefined }}
                    onClick={() => {
                      setFresh(false);
                      setChosen(c.id);
                      if (c.assistantId !== assistantId) navigate(`${ROUTES.assistant}/${c.assistantId}`);
                    }}
                  >
                    <b style={{ fontSize: "12.5px" }}>{c.title}</b>
                    <span className="muted" style={{ fontSize: "11.5px" }}>
                      {c.when}
                    </span>
                  </button>
                );
              })}
              {conversations.length === 0 && (
                <span className="muted" style={{ fontSize: 12, padding: 8 }}>
                  No conversations yet.
                </span>
              )}
            </div>
            <div className="cf" style={{ flexDirection: "column", alignItems: "stretch", gap: "6px" }}>
              <span className="grp" style={{ padding: "0" }}>
                Assistant
              </span>
              {assistants.map((a) => (
                <label key={a.id} className={`radio${a.id === assistantId ? " on" : ""}`}>
                  <input
                    type="radio"
                    name="assistant"
                    value={a.id}
                    checked={a.id === assistantId}
                    onChange={() => {
                      setFresh(false);
                      setChosen(undefined);
                      navigate(`${ROUTES.assistant}/${a.id}`);
                    }}
                  />
                  <span className="rd"></span>
                  <div className="col" style={{ gap: "0" }}>
                    <b style={{ fontSize: "12.5px" }}>{a.name}</b>
                    <span className="muted" style={{ fontSize: "11px" }}>
                      {a.tagline ?? a.description}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* The conversation */}
          <div className="card" style={{ minHeight: "0" }}>
            <div className="ch">
              <span className="av ai">
                <Sparkle size={13} />
              </span>
              <div className="col" style={{ gap: "1px" }}>
                <h3 style={{ fontSize: "14px" }}>{header.name}</h3>
                <span className="muted" style={{ fontSize: "12px" }}>
                  {header.sub}
                </span>
              </div>
              <span className="sp"></span>
              {header.chips.map((c) => (
                <span key={c.text} className={`chip ${c.kind ?? ""}`}>
                  {c.text}
                </span>
              ))}
              {playground && <span className="chip accent">playground</span>}
              <button
                type="button"
                className="btn "
                disabled={conv.handoff.isPending || !conversationId}
                onClick={() => conv.handoff.mutate(undefined, { onError: () => toast.notify("crit", "The handoff could not be made.") })}
              >
                <Person size={14} />
                Talk to a person
              </button>
            </div>
            <div
              ref={scroller}
              className="cb"
              style={{ flex: "1", gap: "18px", padding: "20px 24px", overflowY: "auto" }}
              aria-live="polite"
              aria-busy={busy || undefined}
            >
              {conv.loading && (
                <span className="muted" style={{ fontSize: 13 }}>
                  Opening the conversation…
                </span>
              )}
              {conv.loadError && (
                <div className="banner crit" role="alert">
                  <div>This conversation could not be opened.</div>
                </div>
              )}
              {!conv.loading && conv.turns.length === 0 && (
                <div className="col" style={{ gap: 6, maxWidth: "60ch" }}>
                  <b style={{ fontSize: 14 }}>{`Ask ${header.name.toLowerCase()} anything your role can read.`}</b>
                  <span className="muted" style={{ fontSize: 13 }}>
                    Answers cite their sources; claims without one are marked. Nothing you write here is kept after the session (PD8).
                  </span>
                </div>
              )}
              {conv.turns.map((t) => (
                <div key={t.id} className="turn">
                  {t.role === "user" ? (
                    <span className="av ">{p.initials}</span>
                  ) : (
                    <span className="av ai">
                      <Sparkle size={13} />
                    </span>
                  )}
                  <div className="col" style={{ gap: t.role === "user" ? "4px" : "6px" }}>
                    <div className="who2">
                      {t.role === "user" ? "You" : header.name} <small>{t.role === "user" ? t.at : (t.sourcesLabel ?? sourceCount(t))}</small>
                    </div>
                    {t.views
                      .filter((v) => v.kind === "tool_call")
                      .map((v, i) => (
                        <Aside key={`tc${i}`} view={v} />
                      ))}
                    <Message
                      views={t.views}
                      streaming={t.id === conv.streamingTurnId}
                      sources={t.role === "assistant" && t.id !== conv.streamingTurnId ? sourcesFor(t) : undefined}
                    />
                    {t.views
                      .filter((v) => v.kind !== "tool_call" && v.kind !== "text" && v.kind !== "citation" && v.kind !== "feedback")
                      .map((v, i) => (
                        <Aside key={`as${i}`} view={v} />
                      ))}
                  </div>
                </div>
              ))}
              {conv.error && (
                <div className="banner crit" role="alert">
                  <div>{conv.error}</div>
                </div>
              )}
            </div>
            <div className="cb" style={{ paddingTop: "0", gap: "8px", paddingBottom: "16px" }}>
              <form
                className="compose"
                onSubmit={(e) => {
                  e.preventDefault();
                  doSend();
                }}
              >
                <textarea
                  ref={composer}
                  className="in"
                  rows={1}
                  placeholder="Ask a follow-up…"
                  aria-label="Your message"
                  value={draft}
                  disabled={busy}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    grow(e.target);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      doSend();
                    }
                    if (e.key === "Escape" && busy) conv.stop();
                  }}
                />
                <div className="bar">
                  <span className="muted" style={{ fontSize: "12px" }}>
                    Answers are built from sources your role can read; claims without a source are marked.
                  </span>
                  <span className="sp"></span>
                  {busy ? (
                    <button type="button" className="stopbtn" onClick={conv.stop}>
                      Stop
                    </button>
                  ) : (
                    <button type="submit" className="btn ink s" aria-disabled={!draft.trim() || undefined}>
                      Send
                      <Send size={14} />
                    </button>
                  )}
                </div>
              </form>
              {feedbackView && (
                <div className="fb">
                  <Question size={14} className="i muted" />
                  {feedbackView.question}
                  {conv.answered[feedbackView.seq] === undefined ? (
                    <>
                      <button
                        type="button"
                        className="btn s"
                        disabled={conv.feedback.isPending}
                        onClick={() => conv.feedback.mutate({ seq: feedbackView.seq, yes: true })}
                      >
                        Yes
                      </button>
                      <button
                        type="button"
                        className="btn s"
                        disabled={conv.feedback.isPending}
                        onClick={() => conv.feedback.mutate({ seq: feedbackView.seq, yes: false })}
                      >
                        No
                      </button>
                    </>
                  ) : (
                    <span>{conv.answered[feedbackView.seq] ? "Thanks." : "Thanks · noted for the owner's review."}</span>
                  )}
                  <span className="sp"></span>
                  <span className="faint">one question per turn · your answer trains nothing without review</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}

function sourceCount(t: { views: Array<{ kind: string }> }): string {
  const n = t.views.filter((v) => v.kind === "citation").length;
  return n ? `${n} source${n === 1 ? "" : "s"}` : "";
}
