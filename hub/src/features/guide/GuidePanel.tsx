import { useEffect, useRef, useState } from "react";
import { useFocusTrap } from "../../ui/useFocusTrap";
import { ArrowRight, Check, Close, Play, Send } from "../../ui/icons";
import { useGuide, type Exchange } from "./GuideProvider";
import { pageNote, PERSONAS, STARTERS, TOURS, type Persona, type Step, type StepState } from "./model";

/**
 * The guide's panel: where you are, the one next step, your path, and a place
 * to ask. It is a complementary region, not a modal: the page stays usable
 * beside it, and everything it says is read from the hub's own state or quoted
 * from the collection's pages with the page named.
 */
export function GuidePanel({ steps }: { steps: Array<Step & { state: StepState }> }) {
  const g = useGuide();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    (el.querySelector<HTMLElement>("[data-autofocus]") ?? el).focus();
    // Focus once on open.
  }, []);
  useFocusTrap(panelRef, g.close);

  return (
    <aside id="hub-guide" ref={panelRef} className="guide-panel" aria-label="Guide" tabIndex={-1}>
      <header className="guide-head">
        <span className="guide-mark" aria-hidden="true">
          ✦
        </span>
        <div className="col" style={{ gap: 1, flex: 1, minWidth: 0 }}>
          <b>Guide</b>
          <span className="guide-sub">{g.persona ? PERSONAS.find((p) => p.key === g.persona)?.title : "Let me show you around"}</span>
        </div>
        {g.persona && (
          <button type="button" className="btn g s" onClick={() => g.setPersona(undefined)} title="Change what you are here for">
            Change
          </button>
        )}
        <button type="button" className="btn g s guide-close" aria-label="Close the guide" onClick={g.close}>
          <Close size={14} />
        </button>
      </header>

      {!g.persona ? <Welcome suggested={g.suggested} onPick={g.setPersona} /> : <Body steps={steps} />}

      <footer className="guide-foot">Answers quote the collection's own pages and name them. The guide never acts on your behalf.</footer>
    </aside>
  );
}

function Welcome({ suggested, onPick }: { suggested: Persona; onPick: (p: Persona) => void }) {
  return (
    <div className="guide-body">
      <section className="guide-sec">
        <h3>What brings you here?</h3>
        <p className="guide-p">I'll keep to what matters for you: the pages worth opening, the next step, and answers from our own documentation.</p>
        <div className="guide-choices" role="group" aria-label="What brings you here">
          {PERSONAS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`guide-choice${p.key === suggested ? " suggested" : ""}`}
              onClick={() => onPick(p.key)}
              data-autofocus={p.key === suggested || undefined}
            >
              <b>{p.title}</b>
              <span>{p.sub}</span>
              {p.key === suggested && <em>suggested from your role</em>}
            </button>
          ))}
        </div>
        <p className="guide-p muted">You can change this any time from the top of the panel.</p>
      </section>
    </div>
  );
}

function Body({ steps }: { steps: Array<Step & { state: StepState }> }) {
  const g = useGuide();
  const note = pageNote(g.facts.page);
  const persona = g.facts.persona;
  const done = steps.filter((s) => s.state === "done").length;
  const tour = TOURS[persona];

  const run = (cta: NonNullable<NonNullable<typeof g.nudge>["cta"]>) => {
    if (cta.route) g.go(cta.route);
    else if (cta.ask) g.ask(cta.ask);
    else if (cta.tour) g.startTour(cta.tour);
  };

  return (
    <div className="guide-body">
      <section className="guide-sec">
        <div className="guide-kicker">Where you are</div>
        <h3>{note.title}</h3>
        <p className="guide-p">{note.note[persona]}</p>
      </section>

      {g.nudge && (
        <section className="guide-sec guide-nudge" aria-label="Suggested next step">
          <div className="guide-kicker">Suggested next step</div>
          <p className="guide-p">{g.nudge.text}</p>
          <div className="row" style={{ gap: 8 }}>
            {g.nudge.cta && (
              <button type="button" className="btn p s" onClick={() => run(g.nudge!.cta!)}>
                {g.nudge.cta.label}
                <ArrowRight size={13} />
              </button>
            )}
            <button type="button" className="btn g s" onClick={() => g.dismiss(g.nudge!.id)}>
              Not now
            </button>
          </div>
        </section>
      )}

      <section className="guide-sec">
        <div className="row" style={{ alignItems: "baseline" }}>
          <div className="guide-kicker">Your path</div>
          <span className="sp" />
          <span className="guide-count">
            {done} of {steps.length}
          </span>
        </div>
        <ol className="guide-steps">
          {steps.map((s) => (
            <li key={s.id} className={`guide-step ${s.state}`} aria-current={s.state === "on" ? "step" : undefined}>
              <span className="guide-dot" aria-hidden="true">
                {s.state === "done" ? <Check size={11} /> : null}
              </span>
              <div className="col" style={{ gap: 2, flex: 1, minWidth: 0 }}>
                {s.route || s.ask ? (
                  <button type="button" className="guide-step-title" onClick={() => (s.route ? g.go(s.route) : g.ask(s.ask!))}>
                    {s.title}
                  </button>
                ) : (
                  <span className="guide-step-title">{s.title}</span>
                )}
                {s.state !== "done" && <span className="guide-step-why">{s.why}</span>}
                {s.command && s.state !== "done" && <code className="guide-cmd">{s.command}</code>}
                {s.manual && (
                  <label className="guide-tick">
                    <input type="checkbox" checked={s.state === "done"} onChange={(e) => g.tick(s.id, e.target.checked)} />{" "}
                    {s.state === "done" ? "Done" : "Mark as done"}
                  </label>
                )}
              </div>
            </li>
          ))}
        </ol>
        {tour && (
          <button type="button" className="btn g s" onClick={() => g.startTour(persona)}>
            <Play size={12} />
            {g.facts.toursDone.includes(persona) ? "Show me around again" : "Show me around"}
          </button>
        )}
      </section>

      <Ask />
    </div>
  );
}

function Ask() {
  const g = useGuide();
  const [q, setQ] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const persona = g.facts.persona;

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView?.({ block: "nearest" });
  }, [g.exchanges]);

  const submit = () => {
    if (!q.trim() || g.asking) return;
    g.ask(q);
    setQ("");
  };

  return (
    <section className="guide-sec guide-ask" aria-label="Ask the guide">
      <div className="guide-kicker">Ask</div>
      {g.exchanges.length === 0 ? (
        <div className="guide-starters">
          {STARTERS[persona].map((s) => (
            <button key={s} type="button" className="chip line guide-starter" onClick={() => g.ask(s)}>
              {s}
            </button>
          ))}
        </div>
      ) : (
        <div className="guide-thread" ref={listRef} aria-live="polite">
          {g.exchanges.map((e) => (
            <ExchangeView key={e.id} e={e} />
          ))}
          {g.asking && <div className="guide-a muted">Reading the pages…</div>}
        </div>
      )}
      <form
        className="guide-compose"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          className="ctl"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={persona === "decide" ? "Ask what it can and cannot do…" : persona === "use" ? "Ask how to use the hub…" : "Ask how to build with this…"}
          aria-label="Your question"
          maxLength={2000}
        />
        <button type="submit" className="btn p s" disabled={!q.trim() || g.asking} aria-label="Ask">
          <Send size={14} />
        </button>
      </form>
      {g.exchanges.length > 0 && (
        <button type="button" className="guide-link" onClick={g.clearExchanges}>
          Clear the conversation
        </button>
      )}
    </section>
  );
}

function ExchangeView({ e }: { e: Exchange }) {
  const g = useGuide();
  const a = e.answer;
  return (
    <div className="guide-x">
      <div className="guide-q">{e.question}</div>
      {e.error && <div className="guide-a crit">{e.error}</div>}
      {a && (
        <div className={`guide-a${a.refused ? " refused" : ""}`}>
          {a.answer.split("\n\n").map((para, i) => (
            <p key={i}>{para.split("\n").map((line, j) => (line.startsWith("— ") ? <cite key={j}>{line}</cite> : <span key={j}>{line}</span>))}</p>
          ))}
          {a.sources.length > 0 && (
            <div className="guide-sources">
              <span className="guide-kicker">Sources</span>
              {a.sources.map((s) => (
                <span key={s.id} className="chip mono" title={s.id}>
                  {s.source.split("/").pop()} · {s.section}
                </span>
              ))}
            </div>
          )}
          {a.suggestions.map((s) => (
            <button key={s.route} type="button" className="btn g s guide-go" onClick={() => g.go(s.route)} title={s.why}>
              {s.label}
              <ArrowRight size={12} />
            </button>
          ))}
          {a.note && <span className="guide-note">{a.note}</span>}
        </div>
      )}
    </div>
  );
}
