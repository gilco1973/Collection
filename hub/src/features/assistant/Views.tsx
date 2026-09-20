import type { Chip, Turn, View } from "../../api/types";
import { LinkIcon } from "../../ui/icons";

/**
 * The renderer for the closed descriptor set of specification §8.2. The
 * assistant never sends markup: each `text` leaf is escaped by React and its
 * claims are marked from the spans the harness computed, so a claim without a
 * source is visibly different from one with (PLT-UI-11).
 *
 * Views arrive as a stream. Text leaves flow into paragraphs: a leaf that
 * starts with whitespace continues the current paragraph, any other starts a
 * new one; citations attach to the paragraph they follow.
 */
type Para = Array<{ kind: "text"; view: Extract<View, { kind: "text" }> } | { kind: "citation"; view: Extract<View, { kind: "citation" }> }>;

export function paragraphs(views: View[]): Para[] {
  const out: Para[] = [];
  for (const v of views) {
    if (v.kind === "text") {
      const cont = /^\s/.test(v.text) && out.length > 0;
      if (!cont) out.push([]);
      out[out.length - 1].push({ kind: "text", view: v });
    } else if (v.kind === "citation") {
      if (!out.length) out.push([]);
      out[out.length - 1].push({ kind: "citation", view: v });
    }
  }
  return out;
}

function TextLeaf({ v }: { v: Extract<View, { kind: "text" }> }) {
  const claims = [...(v.claims ?? [])].sort((a, b) => a.span[0] - b.span[0]);
  if (!claims.length) return <>{v.text}</>;
  const parts: React.ReactNode[] = [];
  let i = 0;
  claims.forEach((c, k) => {
    const [s, e] = c.span;
    if (s > i) parts.push(v.text.slice(i, s));
    const cls = c.support === "cited" ? "claim " : c.support === "tool" ? "claim tool" : "claim un";
    parts.push(
      <span
        key={k}
        className={cls}
        title={c.support === "unsupported" ? "No source supports this claim" : c.support === "tool" ? "From a tool result" : "Cited"}
      >
        {v.text.slice(s, e)}
      </span>,
    );
    i = e;
  });
  if (i < v.text.length) parts.push(v.text.slice(i));
  return <>{parts}</>;
}

export function Message({ views, streaming, sources }: { views: View[]; streaming?: boolean; sources?: Chip[] }) {
  const paras = paragraphs(views);
  return (
    <div className="msg">
      {paras.map((p, i) => (
        <p key={i}>
          {p.map((leaf, j) =>
            leaf.kind === "text" ? (
              <TextLeaf key={j} v={leaf.view} />
            ) : (
              <span key={j} className="cite" title={`${leaf.view.classification} · ${leaf.view.chunk_ref}`}>
                <LinkIcon size={11} />
                {leaf.view.source}
              </span>
            ),
          )}
          {streaming && i === paras.length - 1 && <span className="cursor" aria-hidden="true"></span>}
        </p>
      ))}
      {paras.length === 0 && streaming && (
        <p>
          <span className="cursor" aria-hidden="true"></span>
        </p>
      )}
      {sources && sources.length > 0 && (
        <div className="row" style={{ gap: "6px", flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: "12px" }}>
            Sources
          </span>
          {sources.map((c) => (
            <span key={c.text} className={`chip ${c.kind ?? ""}`}>
              {c.text}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Sources row under an answer: the server's chips, or derived from the citations. */
export function sourcesFor(turn: Turn): Chip[] {
  if (turn.sources) return turn.sources;
  const seen = new Map<string, Chip>();
  for (const v of turn.views) {
    if (v.kind !== "citation") continue;
    const kind = v.source.split(" · ")[0].toLowerCase();
    seen.set(`${kind}·${v.classification}`, { text: `${kind} · ${v.classification}`, kind: v.classification === "confidential" ? "model" : "line" });
  }
  return [...seen.values()];
}

const STATE_LABEL: Record<string, string> = {
  proposed: "proposed",
  running: "running…",
  allowed: "allowed",
  denied: "denied",
  pending: "awaiting confirmation",
};

/** Everything in a turn that is not prose: tool calls, budget, stop, handoff, interrupt. */
export function Aside({ view }: { view: View }) {
  switch (view.kind) {
    case "tool_call":
      return (
        <div className="tool">
          <span className="chip mono">{view.tool}</span>
          <span className={`chip ${view.tier === "R" ? "" : view.tier === "W1" ? "warn" : view.tier === "W2" ? "w2" : "money"}`}>{view.tier}</span>
          <span>
            {STATE_LABEL[view.state]}
            {view.ms ? ` · ${view.ms} ms` : ""}
            {view.deny_code ? ` · ${view.deny_code}` : ""}
            {view.args_summary.length ? ` · ${view.args_summary.map((a) => `${a.label}: ${a.value}`).join(", ")}` : ""}
          </span>
        </div>
      );
    case "budget":
      return (
        <div className="budget">{`budget ${fmtK(view.tokens[0])} of ${fmtK(view.tokens[1])} tokens · ${view.tool_calls[0]} of ${view.tool_calls[1]} calls · ${fmtT(view.time_s[0])} of ${fmtT(view.time_s[1])}`}</div>
      );
    case "stop":
      return (
        <div className="banner warn" role="status">
          <div>
            <b>{view.message}</b>
            {view.reason ? ` · ${view.reason}` : ""}
          </div>
        </div>
      );
    case "handoff":
      return (
        <div className="banner accent" role="status">
          <div>
            <b>Handed to a person.</b>
            {` ${view.route === "human" ? "Someone from the desk picks this up" : view.route === "callback" ? "You will be called back" : "Continue by secure message"}${view.expected_wait_s ? ` · about ${Math.round(view.expected_wait_s / 60)} min` : ""}.`}
          </div>
        </div>
      );
    case "interrupt":
      return <div className="budget">{`interrupted at turn ${view.turn}`}</div>;
    case "form":
      return (
        <div className="banner" role="status">
          <div>
            <b>Confirmation needed.</b> This step asks for your confirmation on screen; the form module is not enabled for this assistant.
          </div>
        </div>
      );
    default:
      return null;
  }
}

const fmtK = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`);
const fmtT = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s` : `${s}s`);
