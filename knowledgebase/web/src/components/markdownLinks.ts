import { fileUrl } from "../api/client";

/** Resolve a relative markdown link against the current page path into a docs-relative path. */
export function resolveDocPath(basePath: string, href: string): string {
  const target = href.split("#")[0];
  const dir = basePath.split("/").slice(0, -1);
  for (const part of target.split("/")) {
    if (part === "..") dir.pop();
    else if (part !== "." && part) dir.push(part);
  }
  return dir.join("/");
}

/** Console route for an internal markdown link (directories resolve to their README). */
export function resolveInternal(basePath: string, href: string): string {
  const joined = resolveDocPath(basePath, href);
  return `/kb/page/${joined.endsWith(".md") ? joined : `${joined}/README.md`}`;
}

export type LinkKind =
  | { kind: "internal"; to: string }
  | { kind: "file"; href: string }
  | { kind: "external"; href: string }
  | { kind: "mail"; href: string }
  | { kind: "anchor"; href: string }
  | { kind: "inert" };

const SCHEME = /^([a-z][a-z0-9+.-]*):/i;
const RAW_FILE = /\.(ya?ml|json|csv|txt)$/i;

/** Classify a markdown href so only safe kinds become anchors; everything else is rendered as text. */
export function classifyLink(basePath: string, href: string, catalogFiles?: string[]): LinkKind {
  const trimmed = href.trim();
  if (!trimmed) return { kind: "inert" };
  if (trimmed.startsWith("#")) return { kind: "anchor", href: trimmed };
  const scheme = SCHEME.exec(trimmed)?.[1]?.toLowerCase();
  if (scheme === "http" || scheme === "https") return { kind: "external", href: trimmed };
  if (scheme === "mailto") return { kind: "mail", href: trimmed };
  if (scheme) return { kind: "inert" };
  if (trimmed.startsWith("//")) return { kind: "inert" };
  const path = resolveDocPath(basePath, trimmed);
  if (RAW_FILE.test(path)) return catalogFiles?.includes(path) ? { kind: "file", href: fileUrl(path) } : { kind: "inert" };
  return { kind: "internal", to: resolveInternal(basePath, trimmed) };
}

/** Drop a leading `# Title` that duplicates the page title, so a page has exactly one H1. */
export function stripLeadingHeading(body: string, title: string): string {
  const lines = body.replace(/^\s+/, "").split("\n");
  if (lines[0]?.replace(/^#\s+/, "").trim() === title.trim() && /^#\s/.test(lines[0])) return lines.slice(1).join("\n");
  return body;
}
