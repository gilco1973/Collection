---
title: Review process
owner: model-risk-management
status: active
reviewed: 2026-09-15
tags: [governance]
audience: [everyone]
---
# Review process

## Changing a page

1. Propose the change in source control against the knowledge-base repository.
2. The CI gate runs `kb-librarian check`: frontmatter, structure, links and sensitive
   content. Errors block; warnings are listed for the reviewer.
3. The page owner (from frontmatter) reviews. Changes to governance pages also need
   Model Risk Management; changes to paved roads also need AI Platform Architecture.
4. Merge. Regenerate `docs/index.md` with `kb-librarian index --write` in the same
   change (the CI gate fails when the index is out of date). The weekly live audit
   mirrors configured sections to Confluence; a nightly dry run only reports.

## Keeping a page current

- Each section has a review window (`review_every_days` in `kb.config.yaml`).
- The librarian flags pages past their window to the owner and, in live audits with
  Atlassian enabled, opens a Jira issue in `AIKB`.
- The owner re-reads the page, fixes what changed, and bumps `reviewed`. Only an owner
  bumps `reviewed`; the librarian never does.

## Raising a finding as a reader

Open a Jira issue in `AIKB` with the page path and what is wrong, or propose the fix
directly. Either is welcome; the review is the same.

## Escalation

Disagreements about content go to the owning team's lead; disagreements about
governance go to Model Risk Management. Decisions that change the platform's shape are
recorded as [decision records](../wiki/decision-records/README.md).
