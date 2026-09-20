---
title: Taxonomy
owner: model-risk-management
status: active
reviewed: 2026-09-15
tags: [governance]
audience: [everyone]
---
# Taxonomy

The tags and audiences a page may declare. The authoritative list is
`taxonomy.tags` and `frontmatter.audience_values` in `kb.config.yaml`; this page explains them.

## Tags

| Tag | Use for |
| --- | --- |
| onboarding | Pages a new joiner reads in their first 90 days |
| paved-road | An approved architecture |
| best-practice | A practice that applies on every road |
| security | Threats and controls |
| governance | Rules, roles, processes |
| model-risk | Model risk management content |
| prompting | Prompt design |
| agents | Agent design and runtime |
| rag | Retrieval-augmented generation |
| evaluation | Evaluation sets, graders, pipelines |
| observability | Monitoring, logging, alerting |
| cost | Spend and efficiency |
| atlassian | Confluence and Jira integration |
| tutorial | Hands-on, ordered exercises |
| video | Recorded sessions |
| skill | Skill folders and their catalog |
| glossary | Term definitions |
| adr | Decision records |
| faq | Questions and answers |
| data | Data handling and classification |

## Audiences

`new-hire`, `engineer`, `data-scientist`, `product`, `risk`, `leadership`, `everyone`.

## Changing the taxonomy

Propose the change to `kb.config.yaml` and this page together. Model Risk Management
and AI Platform Enablement sign off. The librarian flags any page using a tag that is
not in the list, so add the tag before the page that uses it.
