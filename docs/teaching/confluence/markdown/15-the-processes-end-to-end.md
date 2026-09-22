# 15. The processes, end to end

*Four pictures of how things move.*

## An initiative, from idea to production

![diagram](../attachments/15-the-processes-end-to-end/15-the-processes-end-to-end-01-19cce4f2.png)

```mermaid
flowchart LR
  A[A team feels a problem] --> B[Champion writes the brief<br/>Build → Intake, 15 min]
  B --> C{Reads only?}
  C -- yes --> D[Champion files it]
  C -- no --> E[Team lead files it]
  D --> F[Platform lead confirms the road<br/>within two working days]
  E --> F
  F --> G[Build from the collection<br/>on the road, embedded engineer]
  G --> H[Sandbox and evaluation<br/>a failed gate returns to Build]
  H --> I[Production, read-only first]
  I --> J[Something returned to the collection]
```

## A component's way to the shelf

![diagram](../attachments/15-the-processes-end-to-end/15-the-processes-end-to-end-02-6983e8e2.png)

```mermaid
flowchart LR
  S[Scaffolded] --> B[Built<br/>tests green, status ready] --> U[Used once for real<br/>owner names the project] --> O[Owner signed] --> A[AI security signed] --> G[On the shelf<br/>GA on Discover]
  G -. a new version .-> U
```

## How an answer is produced

![diagram](../attachments/15-the-processes-end-to-end/15-the-processes-end-to-end-03-3f63829d.png)

```mermaid
flowchart LR
  Q[Your question] --> G[Guard scores it<br/>and every source for instructions]
  G -- looks like an instruction --> X[Stopped, not used]
  G --> K[Knowledge base searched<br/>pages fenced as sources]
  K --> M[Model answers from<br/>the sources only]
  M --> C[Every claim cited<br/>or dropped]
  C --> A[The answer, sources shown]
```

## What stops an agent

![diagram](../attachments/15-the-processes-end-to-end/15-the-processes-end-to-end-04-206ae7dc.png)

```mermaid
flowchart LR
  T[Agent proposes a call] --> H{In the signed catalog?}
  H -- no --> R1[Refused]
  H -- yes --> P{Tier}
  P -- R --> RUN[Runs]
  P -- W1 --> W[Parked until the person<br/>confirms that exact action, once]
  P -- W2 --> S[Needs a second named person]
  P -- MONEY --> R2[Refused]
  W --> REC[Everything lands on the chained record]
  RUN --> REC
  S --> REC
```
