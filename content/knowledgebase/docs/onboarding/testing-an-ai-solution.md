---
title: Testing an AI solution before it is onboarded
owner: ai-platform-enablement
status: active
reviewed: '2026-09-22'
tags: [onboarding, security, evaluation, agents]
audience: [engineer]
---
# Testing an AI solution before it is onboarded

Before a component is signed, the solution it becomes is put through the playground: the collection's test bench,
kept beside the components in the repository. One run answers three questions a signer would otherwise answer by
reading code: does the candidate meet the collection's contract, does the running solution hold under attack, and
does it do its job. The answer is a report with a verdict, read by both signers before they sign.

The report is evidence, never a sign-off. [Onboarding components](component-onboarding.md) is still the process:
two named people sign each version, and the manifest records it.

## Who runs it, and when

- **The engineer** runs it while building, and attaches the last report to the pull request that asks for sign-off.
- **The AI security engineer** runs it again with every probe, triages what needs a person, and cites the report's id in the sign-off note.
- **Anyone** can run it on a solution that is not a component yet, to see where it stands before writing a brief.

## What one run does

1. **The contract**: the manifest, the README's headings, sign-offs untouched, imports that stay inside the component, no secrets, no real identifiers or addresses, no money tool in an agent's template, and the component's own tests and live example run in a throwaway copy.
2. **The probes**: prompt injection (direct, hidden in a document or a record, encoded, obfuscated, role-play, split), disclosure (a secret in the instructions, the instructions themselves, a credential or personal data in a source), output handling (a remote image that sends data out, active content), excessive agency (moving money, a destructive action a document asks for), grounding, robustness, and, for tool servers, schemas, poisoned descriptions, bad and hostile arguments, and whether the server survives.
3. **Your cases**: what the solution is for, as questions (or tool calls) and what a good answer contains, cites or refuses.

Each probe plants something unique, such as a marker, a canary or a fake card number, and judges the answer by
looking for it. The wording of the answer never decides a verdict. Where only a person can judge, the result is
marked for review rather than guessed.

## The rules it keeps

- **Never production.** The target must be a sandbox, development, test or staging environment; probes are adversarial.
- **Only hosts you name.** Anything beyond the local machine must be listed in the target's allowed hosts.
- **Credentials are names.** A secret is written as the name of an environment variable; any value that comes back is replaced in the report.
- **A person decides what a probe cannot.** Triage records a named person, a decision and a reason; a critical or high risk is accepted by someone other than the tester.

## Reading the verdict

| Verdict | Meaning | What happens next |
| --- | --- | --- |
| clear | Everything that applies held, or was triaged by a named person | Ask for the two sign-offs |
| needs review | A medium or low failure, a result marked for review, or a probe that could not run | Fix it, or have it triaged, then ask |
| blocked | A critical or high finding failed and nobody has triaged it | Not signed; fix it and run again |
| incomplete | The solution could not be reached | Check the target and run again |

An accepted risk does not disappear: the report lists it under the known limits to add, and the owner copies it
into the component's README, where the next reader finds it.

## Checks before asking for a sign-off

- The last report is clear, or every open finding is triaged by name.
- The report is of the version being signed.
- Accepted risks are in the README's known limits.
- The report's id is in the pull request, for the AI security engineer to cite.
