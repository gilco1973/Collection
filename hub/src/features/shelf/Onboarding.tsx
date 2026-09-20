import { Link } from "react-router-dom";
import type { ShelfEntry } from "../../api/types";
import { env } from "../../config/env";
import { ROUTES } from "../../routes";
import { Crumbs, HubFoot, HubNav } from "../../ui/HubChrome";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useTitle } from "../../ui/useTitle";
import { STAGE_LABELS, groupByStage } from "./stages";
import { useShelf } from "./useShelf";

const KB = (path: string) => `${env.VITE_KB_URL}${path}`;

/** What each stage needs before the next; the same words as CONTRIBUTING.md. */
const STAGE_PROOF = [
  "a manifest from the scaffold: version 0.1.0, both sign-offs pending, a spec entry, a tag from the taxonomy",
  "README, walkthrough, live example and tests filled and green; status set to ready",
  "used in one real project, named in the manifest (used_in) by the owner",
  "the owner signs at this version after running the tests and the example",
  "an AI security engineer signs at this version after reading the rules and the walkthrough and running the example",
  "listed as GA on Discover and in the knowledge base; a version bump asks both to sign again",
];

/**
 * The onboarding tracker: where every component is on its way to the shelf,
 * and how a person joins as a champion, an owner or an AI security engineer.
 */
export default function Onboarding() {
  const palette = usePalette();
  const q = useShelf();
  useTitle("Onboarding");

  if (q.isPending) return <PageState kind="loading" text="Reading the shelf…" />;
  if (q.error || !q.data) return <PageState kind="error" text="The shelf could not be read." detail={(q.error as Error)?.message} />;
  const groups = groupByStage(q.data);
  const onShelf = q.data.filter((e) => e.signed).length;

  return (
    <div className="hub" data-live style={{ minHeight: "1400px" }}>
      <HubNav active="Build" onSearch={palette.open} />
      <div className="hwrap">
        <Crumbs area="Build" page="Onboarding" />
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "600", letterSpacing: "-.02em" }}>Onboarding</h1>
            <div className="muted" style={{ fontSize: "14px", marginTop: "4px" }}>
              Two things are onboarded here: components, on their way to the shelf, and people, into the roles that put them there.
            </div>
          </div>
          <span className="sp"></span>
          <span className="chip ok">
            {onShelf} of {q.data.length} on the shelf
          </span>
        </div>

        <div className="card">
          <div className="ch">
            <h3>A component's way to the shelf</h3>
            <span className="sp"></span>
            <Link to={ROUTES.shelfSignoffs} className="btn g s">
              Sign-off queue
            </Link>
          </div>
          <div className="cb">
            <div className="steps" style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(0,1fr))", gap: 12 }}>
              {STAGE_LABELS.map((label, i) => (
                <div key={label} className="step">
                  <span className="n">{i + 1}</span>
                  <span className="t">
                    {label}
                    <small>{STAGE_PROOF[i]}</small>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 380px", gap: "24px", minHeight: "0" }}>
          <div className="col" style={{ gap: 16, minWidth: 0 }}>
            {groups.map((g) => (
              <div key={g.key} className="card">
                <div className="ch">
                  <h3>{g.title}</h3>
                  <span className="sp"></span>
                  <span className="chip line">{g.entries.length}</span>
                </div>
                <div className="cb" style={{ gap: 10 }}>
                  <div className="muted" style={{ fontSize: 12.5 }}>
                    {g.note}
                  </div>
                  {g.entries.map((e) => (
                    <Progress key={e.name} e={e} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="col" style={{ gap: 16 }}>
            <People
              title="A new champion"
              chip="week one"
              items={[
                ["Read the programme page and the cadence", KB("/kb/page/onboarding/ai-champions.md")],
                ["Sign in here, open Discover, and run one live example from the Tools tab", ROUTES.discover],
                ["Start an initiative brief for your team's first use", ROUTES.intake],
                ["Read the component onboarding page: stages, sign-offs, who signs", KB("/kb/page/onboarding/component-onboarding.md")],
                ["Bring one thing to the next meeting: a demonstration, a page, or a component scaffold", ROUTES.learn],
              ]}
            />
            <People
              title="A component owner"
              chip="by name"
              items={[
                ["Your handle is the manifest's owner field; that is what lets you sign", ROUTES.shelfSignoffs],
                ["Keep the README's known limits honest; bump the version on any change a consumer would notice", KB("/kb/page/components/README.md")],
                ["Use it once for real and sign; a stale sign-off after a bump is yours to renew", ROUTES.shelfSignoffs],
                ["Answer questions in the champions channel; the listing names you as support", ROUTES.discover],
              ]}
            />
            <People
              title="An AI security engineer"
              chip="ai.security"
              items={[
                ["Ask the security team lead for the ai.security role on your platform principal", ROUTES.settings],
                ["Read the security practices the components enforce before your first review", KB("/kb/page/best-practices/README.md")],
                ["For each component: read the rules and the walkthrough, run the tests and the example, then sign", ROUTES.shelfSignoffs],
                ["Say in the note what you looked at hardest; the owner fixes it in the next version", ROUTES.shelfSignoffs],
              ]}
            />
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}

function Progress({ e }: { e: ShelfEntry }) {
  const done = e.status === "deprecated" ? STAGE_LABELS.length : e.stage.index;
  return (
    <div className="row" style={{ gap: 12, alignItems: "flex-start", fontSize: 13 }}>
      <div style={{ width: 220, flex: "none" }}>
        <Link to={e.hubPath}>{e.title}</Link>
        <div className="muted" style={{ fontSize: 12 }}>
          <span className="mono">{e.version}</span> · {e.kind} · owner {e.owner}
          {e.usedIn.length > 0 ? ` · used in ${e.usedIn.join(", ")}` : ""}
        </div>
      </div>
      <div className="row" style={{ gap: 4 }} aria-label={`stage ${done} of ${STAGE_LABELS.length}`}>
        {STAGE_LABELS.map((l, i) => (
          <span
            key={l}
            title={l}
            style={{ width: 22, height: 6, borderRadius: 3, background: i < done ? "var(--ok)" : i === done ? "var(--warn)" : "var(--surface-3)" }}
          />
        ))}
      </div>
      <span className="muted" style={{ fontSize: 12.5, flex: 1 }}>
        next: {e.stage.next}
      </span>
    </div>
  );
}

function People({ title, chip, items }: { title: string; chip: string; items: Array<[string, string]> }) {
  return (
    <div className="card">
      <div className="ch">
        <h3>{title}</h3>
        <span className="sp"></span>
        <span className="chip mono">{chip}</span>
      </div>
      <div className="cb">
        <div className="steps">
          {items.map(([text, to], i) => (
            <div key={text} className="step">
              <span className="n">{i + 1}</span>
              <span className="t">{to.startsWith("/") ? <Link to={to}>{text}</Link> : <a href={to}>{text}</a>}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
