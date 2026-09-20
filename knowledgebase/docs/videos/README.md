---
title: Videos
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [video, onboarding]
audience: [new-hire, everyone]
---
# Videos

Recorded internal sessions, paired with the [reading list](../onboarding/reading-list.md).
Watch after the reading. The catalog lives in [catalog.yaml](catalog.yaml) so the
librarian and the learning platform can read it.

## Rules for entries

- Videos are hosted on the approved internal video platform; links to consumer video
  sites are not accepted in the catalog.
- Each entry has an owner, a recording date, a duration, the reading-list block it
  supports, and a `status` (`placeholder`, `scheduled`, `available`, `retired`). The
  catalog ships with every session as a `placeholder`: the URLs point at
  `video.internal.example` and must be replaced when the recording exists.
- Sessions older than 18 months are re-reviewed by their owner or retired.

## Current series

| Series | Supports | Sessions |
| --- | --- | --- |
| Welcome to AI at the bank | Reading block 1 | Governance in 20 minutes; The gateway, live; Data classification with real examples |
| Building on the paved roads | Reading block 2 | Assistant service walkthrough; RAG service walkthrough; Agent with tools, including the librarian |
| Evaluations | Reading block 1 and 2 | Your first evaluation set; Model-graded rubrics that hold up |
| Model risk for engineers | Reading block 2 | What validators look for; Tiering a use case |

## Contributing

Record the session, add the entry to `catalog.yaml`, and submit through the
[review process](../governance/review-process.md). The librarian's `catalogs` check
validates the schema, dates and URL hosts on every run.
