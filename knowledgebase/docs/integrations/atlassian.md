---
title: Atlassian integration
owner: ai-platform-engineering
status: active
reviewed: 2026-09-15
tags: [atlassian, governance]
audience: [engineer, everyone]
---
# Atlassian integration

## What it does

| Direction | What | How |
| --- | --- | --- |
| Knowledge base → Confluence | Mirrors the sections listed under `atlassian.mirror_sections` in `kb.config.yaml` into space `AIKB` as pages titled `[Section] Title` | `kb-librarian atlassian sync` |
| Knowledge base → Jira | Creates one issue per finding that needs an owner (stale page, missing section landing page, unresolvable link) | The librarian's `jira_create_issue` tool during a live audit with `--atlassian` |
| Confluence → librarian | Search and read pages so the librarian can spot duplicated or contradicting content | The `confluence_search` and `confluence_get_page` tools |

The mirrored pages carry a footer naming the source page. Edits belong in the source;
the next sync overwrites the copy.

## Configuration

Set in the environment (from the secret manager, never in a file that is committed):

```
KB_ATLASSIAN_BASE_URL=https://<tenant>.atlassian.net
KB_ATLASSIAN_EMAIL=<service account email>
KB_ATLASSIAN_API_TOKEN=<api token>
KB_ATLASSIAN_ALLOW_WRITE=false
```

Space and project keys come from `kb.config.yaml` (`atlassian.confluence_space_key`,
`atlassian.jira_project_key`).

## The write gate

Reads work as soon as credentials are present. Writes require **both**
`KB_ATLASSIAN_ALLOW_WRITE=true` and a live (non dry-run) run, which itself requires
`KB_ALLOW_LIVE=true`. Otherwise the clients refuse before any request is sent and report
`would-publish`. The gate is client-side: it stops the librarian from writing by
accident, not a stolen token from being used elsewhere. Least privilege on the account
does that.

## Service accounts

Two dedicated Atlassian service accounts, both limited to space `AIKB` and project `AIKB`:

- **read-only** — used by every audit and by the nightly workflow. Its token cannot
  create or edit anything even if it leaks.
- **write-capable** — injected only into the weekly live job and into an operator's
  shell for a deliberate `atlassian sync --live`.

Token rotation follows the standard credential rotation schedule.

## Running a sync

```bash
kb-librarian atlassian sync                 # dry run: lists what would be published
KB_ALLOW_LIVE=true KB_ATLASSIAN_ALLOW_WRITE=true kb-librarian atlassian sync --live
```

Only pages with `status: active` are mirrored; drafts and deprecated pages are skipped.
