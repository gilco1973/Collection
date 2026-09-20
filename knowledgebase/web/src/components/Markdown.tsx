import { useTranslation } from "react-i18next";
import { inline, type InlineOptions } from "./markdownInline";

const HEADING = /^(#{1,6})\s+(.+)$/;
const FENCE = /^(```|~~~)/;
const LIST_ITEM = /^(\s*)([-*+]|\d+\.)\s+(.*)$/;
const ALIGN_ROW = /^\s*:?-+:?\s*$/;
const HR = /^\s*([-*_])(\s*\1){2,}\s*$/;

const isBlockStart = (line: string) =>
  HEADING.test(line) || FENCE.test(line) || line.startsWith("|") || LIST_ITEM.test(line) || line.startsWith(">") || HR.test(line);

const alignClass = (spec: string | undefined) => {
  if (!spec) return "text-start";
  const left = spec.trim().startsWith(":");
  const right = spec.trim().endsWith(":");
  return left && right ? "text-center" : right ? "text-end" : "text-start";
};

function renderTable(lines: string[], key: number, opts: InlineOptions) {
  const rows: string[][] = [];
  let aligns: string[] = [];
  for (const raw of lines) {
    const cells = raw.split("|").slice(1, -1).map((c) => c.trim());
    if (cells.length && cells.every((c) => ALIGN_ROW.test(c))) aligns = cells;
    else rows.push(cells);
  }
  return (
    <div key={key} className="my-3 overflow-x-auto">
      <table className="min-w-full text-[13px]">
        <thead><tr>{rows[0]?.map((c, n) => <th key={n} className={`border-b border-rule px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted ${alignClass(aligns[n])}`}>{inline(c, `th${key}-${n}`, opts)}</th>)}</tr></thead>
        <tbody>{rows.slice(1).map((r, rn) => <tr key={rn}>{r.map((c, n) => <td key={n} className={`border-b border-rule px-2 py-1.5 align-top ${alignClass(aligns[n])}`}>{inline(c, `td${key}-${rn}-${n}`, opts)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

interface Item { text: string; children: string[] }

function renderList(lines: string[], key: number, opts: InlineOptions) {
  const ordered = /^\s*\d+\./.test(lines[0]);
  const items: Item[] = [];
  for (const line of lines) {
    const m = LIST_ITEM.exec(line)!;
    if (m[1].length >= 2 && items.length) items[items.length - 1].children.push(m[3]);
    else items.push({ text: m[3], children: [] });
  }
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag key={key} className={`my-2 ms-6 ${ordered ? "list-decimal" : "list-disc"}`}>
      {items.map((it, n) => (
        <li key={n}>
          {inline(it.text, `li${key}-${n}`, opts)}
          {it.children.length > 0 && <ul className="ms-6 list-[circle]">{it.children.map((c, cn) => <li key={cn}>{inline(c, `li${key}-${n}-${cn}`, opts)}</li>)}</ul>}
        </li>
      ))}
    </Tag>
  );
}

interface Props { source: string; basePath: string; plainLinks?: boolean; catalogFiles?: string[] }

/** Block-level markdown. Body H1s are demoted to H2 because the page title owns the H1. */
export default function Markdown({ source, basePath, plainLinks, catalogFiles }: Props) {
  const { t } = useTranslation();
  const opts: InlineOptions = { basePath, plainLinks, catalogFiles, externalHint: t("common.opensExternal") };
  const blocks: React.ReactNode[] = [];
  const lines = source.split("\n");
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const start = i;
    const line = lines[i];
    const heading = HEADING.exec(line);
    if (FENCE.test(line)) {
      const fence = line.slice(0, 3);
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith(fence)) code.push(lines[i++]);
      i++;
      blocks.push(<pre key={key++} dir="ltr" className="overflow-x-auto rounded-s border border-rule bg-surface-2 p-3 font-mono text-[12.5px] leading-[1.5] text-ink"><code>{code.join("\n")}</code></pre>);
    } else if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      const size = ["text-[20px]", "text-[17px]", "text-[15px]", "text-[14px]", "text-[14px]"][level - 2];
      blocks.push(<Tag key={key++} className={`mb-2 mt-7 font-semibold tracking-[-0.01em] text-ink ${size}`}>{inline(heading[2], `h${key}`, opts)}</Tag>);
      i++;
    } else if (HR.test(line)) {
      blocks.push(<hr key={key++} className="my-4 border-rule" />);
      i++;
    } else if (LIST_ITEM.test(line)) {
      const items: string[] = [];
      while (i < lines.length && LIST_ITEM.test(lines[i])) items.push(lines[i++]);
      blocks.push(renderList(items, key++, opts));
    } else if (line.startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      blocks.push(renderTable(rows, key++, opts));
    } else if (line.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={key++} className="my-3 border-s-2 border-rule-2 ps-3 text-muted">{inline(quote.join(" "), `q${key}`, opts)}</blockquote>);
    } else if (!line.trim()) {
      i++;
    } else {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && (i === start || !isBlockStart(lines[i]))) para.push(lines[i++]);
      blocks.push(<p key={key++} className="my-3 max-w-[72ch]">{inline(para.join(" "), `p${key}`, opts)}</p>);
    }
    if (i === start) i++; // defensive: every branch must consume input
  }
  return <div className="max-w-3xl break-words">{blocks}</div>;
}
