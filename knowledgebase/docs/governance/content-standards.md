---
title: Content standards
owner: model-risk-management
status: active
reviewed: 2026-09-15
tags: [governance]
audience: [everyone]
---
# Content standards

Every page in this knowledge base:

1. **Has frontmatter** with `title`, `owner`, `status`, `reviewed`, `tags`, `audience`.
   `status` is `draft`, `active` or `deprecated`; `reviewed` is an ISO date; `tags` come
   from the [taxonomy](taxonomy.md).
2. **Is Internal tier.** No Confidential or Restricted content, no credentials, no
   personal data, no customer data, in text, examples or screenshots. The librarian's
   sensitive-content check fails the build on a critical hit.
3. **Is reachable.** Linked from its section landing page or the index. Orphans are findings.
4. **Links resolve.** Internal links point at existing pages. External links use hosts
   in `links.trusted_hosts` or are marked unverified.
5. **Is short.** Under 200 lines. Split rather than scroll.
6. **Says who and when.** Owner in frontmatter; review cadence from the section.
7. **Prefers rules to narrative.** State what to do; link to why.
8. **Deprecates rather than deletes.** Set `status: deprecated`, link the replacement,
   keep the page one review cycle, then remove it through the review process.

## Section landing pages

Each section has a `README.md` that lists its pages in reading order with one line each.

## Examples and code

Code samples use the internal SDK bundle and gateway names. They are illustrative; a
tutorial's code is tested, a practice page's code is not, and the page says which.
