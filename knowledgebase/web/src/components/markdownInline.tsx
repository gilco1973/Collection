import { Link } from "react-router-dom";
import { classifyLink } from "./markdownLinks";

export interface InlineOptions {
  basePath: string;
  /** Render links as plain text (used for model-authored summaries, which must never be clickable). */
  plainLinks?: boolean;
  /** Docs-relative paths the API serves raw (the contract's catalogs); other raw-file links stay inert. */
  catalogFiles?: string[];
  /** Screen-reader suffix for links that open a new tab. */
  externalHint?: string;
}

const LINK_CLASS = "text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent";
// Order matters: code, image, link, bold, italics. The URL class excludes "(" so one balanced
// parenthesised segment can follow without an ambiguous (quadratic) split between two runs.
export const TOKEN = /(`[^`]+`)|(!\[([^\]]*)\]\(([^()\s]+)\))|(\[([^\]]+)\]\(([^()\s]+(?:\([^()\s]*\)[^()\s]*)?)\))|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)/g;

function renderLink(label: string, href: string, key: string, opts: InlineOptions): React.ReactNode {
  const target = classifyLink(opts.basePath, href, opts.catalogFiles);
  if (opts.plainLinks) return <span key={key}>{target.kind === "inert" ? label : `${label} (${href})`}</span>;
  switch (target.kind) {
    case "internal":
      return <Link key={key} to={target.to} className={LINK_CLASS}>{label}</Link>;
    case "external":
      return (
        <a key={key} href={target.href} target="_blank" rel="noreferrer noopener" className={LINK_CLASS}>
          {label}{opts.externalHint && <span className="sr-only"> ({opts.externalHint})</span>}
        </a>
      );
    case "file":
    case "mail":
    case "anchor":
      return <a key={key} href={target.href} className={LINK_CLASS}>{label}</a>;
    default:
      return <span key={key}>{label}</span>;
  }
}

/** Minimal, safe inline markdown: no raw HTML is ever injected. */
export function inline(text: string, keyPrefix: string, opts: InlineOptions): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  let n = 0;
  let match: RegExpExecArray | null;
  TOKEN.lastIndex = 0;
  while ((match = TOKEN.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const key = `${keyPrefix}-${n++}`;
    if (match[1]) parts.push(<code key={key} dir="ltr" className="rounded-[4px] bg-surface-3 px-1 font-mono text-[12px]">{match[1].slice(1, -1)}</code>);
    else if (match[2]) parts.push(<span key={key} className="italic text-muted">[{match[3] || match[4]}]</span>);
    else if (match[5]) parts.push(renderLink(match[6], match[7], key, opts));
    else if (match[8]) parts.push(<strong key={key}>{match[8].slice(2, -2)}</strong>);
    else if (match[9]) parts.push(<em key={key}>{match[9].slice(1, -1)}</em>);
    last = TOKEN.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
