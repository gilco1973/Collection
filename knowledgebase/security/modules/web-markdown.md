# Security review sheet: Markdown renderer and link classification

| | |
| --- | --- |
| Module id | `web-markdown` |
| Kind | frontend |
| Code | `web/src/components/Markdown.tsx`, `markdownInline.tsx`, `markdownLinks.ts` |
| Tests | `web/src/test/units.test.ts` (link classification), `web/src/test/pageview.test.tsx` |
| Depends on | React, react-router (`Link`) |

## Purpose

Renders page bodies and the model's audit summary as React elements from a deliberately small
Markdown subset: headings (demoted one level), paragraphs, fenced code, lists (one nesting
level), tables, blockquotes, horizontal rules; inline code, images (as a text placeholder),
links, bold, italics. **No HTML is ever parsed or injected.**

## Entry points

`<Markdown source basePath plainLinks? catalogFiles? />`, `classifyLink`, `resolveDocPath`,
`resolveInternal`, `stripLeadingHeading`.

## Trust boundaries

`source` is untrusted: page authors, machine translations, and — with `plainLinks` — the
model's own summary text.

## Data handled

Page/summary text only.

## Secrets

None.

## External calls

None. External links render as `<a target="_blank" rel="noreferrer noopener">` with a
screen-reader hint; navigation is the user's click.

## Mutations

None.

## Controls in place

- Output is built from React elements and strings — raw HTML in the source is shown as text.
- `classifyLink` allow-lists link kinds: `#anchor`, `http(s)` external, `mailto`, internal
  docs-relative paths (resolved with `..` handling, directories → `README.md`), raw files only
  when the path is one of the contract's catalogs (served by `/api/files`); **every other
  scheme (`javascript:`, `data:`, `vbscript:`, …) and protocol-relative `//` URLs are inert**
  (rendered as text).
- `plainLinks` (audit summaries): links are never clickable; the target is shown in parentheses.
- Images are not fetched: rendered as `[alt]` placeholder text (no `<img>`), so a page cannot
  make the reader's browser request an arbitrary URL.
- The inline tokenizer's URL class excludes `(` so pathological input cannot cause quadratic
  backtracking.

## Residual risks and reviewer attention points

- External `http(s)` links are clickable by design; a page may link to a phishing site — the
  content review process (`kb-librarian check` link checks with trusted hosts) is the control,
  and the link opens in a new tab with `noopener`.
- Nested constructs beyond the subset render as plain text (safe, possibly ugly).

## Reviewer checklist

- [ ] No `dangerouslySetInnerHTML` / `innerHTML` in these files.
- [ ] `classifyLink` still returns `inert` for any unknown scheme and for `//`.
- [ ] Images remain placeholders (no `<img>` element).

## Sign-off

Submit with `kb-librarian security submit web-markdown`; the reviewer records the decision with
`kb-librarian security sign web-markdown …`, which appends a row here and to `security/signoffs/web-markdown.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
