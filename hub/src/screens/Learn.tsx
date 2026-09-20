import { Link } from "react-router-dom";
import { env } from "../config/env";
import { ROUTES } from "../routes";
import { usePalette } from "../ui/CommandPalette";
import { HubFoot, HubNav } from "../ui/HubChrome";
import { ArrowRight } from "../ui/icons";
import { useTitle } from "../ui/useTitle";

/**
 * Learn is the one Hub area without an artboard in the design canvas. It
 * carries what the other screens link to (the six roads, this week's updates,
 * the 15-minute example) on the same chrome, so no link is dead. Content is
 * the platform team's (PLT-ONB-12 modules are the consumer teams').
 */
const ROADS = [
  { id: "R1", name: "Tools and knowledge", who: "a service that exposes tools or a corpus; no model of its own", weeks: "2 weeks to sandbox" },
  { id: "R2", name: "Internal agent", who: "an agent with tools for staff; read or write profiles; ladder L0–L2", weeks: "3 weeks to sandbox" },
  { id: "R3", name: "Customer and partner assistant", who: "federated identity, entitlements, step-up, handoff; Phase 5", weeks: "6 weeks to sandbox" },
  { id: "R4", name: "Batch agent with a review queue", who: "scheduled drafting into a queue a person samples", weeks: "2 weeks to sandbox" },
  { id: "R5", name: "Retrieval service", who: "a governed corpus with provenance on every chunk", weeks: "2 weeks to sandbox" },
  { id: "R6", name: "Existing solution onboarding", who: "an AI solution that already has a surface; depths D1–D4 (§7.14)", weeks: "by wave" },
];

export default function Learn() {
  const palette = usePalette();
  useTitle("Learn");
  return (
    <div className="hub" data-live style={{ minHeight: "900px" }}>
      <HubNav active="Learn" onSearch={palette.open} />
      <div className="hwrap">
        <div className="hsec">
          <div className="hh">
            <h2>Learn</h2>
            <span className="sub">roads, bootcamp, office hours and what changed</span>
            <span className="sp"></span>
          </div>
          <div className="banner accent">
            <div>Enablement modules for each consumer (PLT-ONB-12) are reached from its listing; this page holds the platform's own material.</div>
          </div>
        </div>
        <div className="hsec" id="roads">
          <div className="hh">
            <h2>The six roads</h2>
            <span className="sub">pick one in the brief; the repository, gates and reviews follow from it</span>
            <span className="sp"></span>
            <Link className="btn s" to={ROUTES.intake}>
              Start a brief
              <ArrowRight size={14} />
            </Link>
          </div>
          <table className="t ">
            <thead>
              <tr>
                <th>Road</th>
                <th>For</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {ROADS.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span className="chip line">{r.id}</span> <b style={{ marginLeft: 6 }}>{r.name}</b>
                  </td>
                  <td style={{ whiteSpace: "normal" }}>{r.who}</td>
                  <td className="muted">{r.weeks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="hsec" id="collection">
          <div className="hh">
            <h2>The collection and the knowledge base</h2>
            <span className="sub">reusable components, the practices behind them, and the AI champions programme</span>
            <span className="sp"></span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
            <div className="card">
              <div className="ch">
                <h3>Reusable components</h3>
                <span className="sp"></span>
                <span className="chip line">R1</span>
              </div>
              <div className="cb" style={{ fontSize: 13 }}>
                Tools, integrations and patterns lifted from products in production: a governed action loop, an untrusted-input guard, connectors, an API client. Each with a five-minute README and tests, under the Tools and Knowledge tabs and in search.{" "}
                <Link to={ROUTES.discover}>Open Discover</Link>
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>The knowledge base</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ fontSize: 13 }}>
                Best practices, paved roads, the agent skills catalog, tutorials and governance, kept healthy by the librarian. Every component's page is published there too.{" "}
                <a href={env.VITE_KB_URL}>Open the knowledge base</a>
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>AI champions</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ fontSize: 13 }}>
                One engineer per team, meeting every two weeks to pick one initiative each, build it from the collection on a paved road, and bring the result back. The charter and the initiative brief are in the knowledge base under onboarding.{" "}
                <Link to={ROUTES.intake}>Start a brief</Link>
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div className="card" id="example">
            <div className="ch">
              <h3>The 15-minute example</h3>
              <span className="sp"></span>
              <span className="chip mono">R2</span>
            </div>
            <div className="cb" style={{ fontSize: 13 }}>
              <div className="steps">
                <div className="step">
                  <span className="n">1</span>
                  <span className="t">
                    Get a playground key<small>My workspace → Playground · per-developer budget</small>
                  </span>
                </div>
                <div className="step">
                  <span className="n">2</span>
                  <span className="t">
                    Run the example against the sandbox gateway<small>reads COS fixtures with your identity; every call is attributed</small>
                  </span>
                </div>
                <div className="step">
                  <span className="n">3</span>
                  <span className="t">
                    Change one tool, run again<small>see the policy decision, the audit entry and the cost</small>
                  </span>
                </div>
              </div>
              <Link to={ROUTES.workspace}>
                Open my workspace
                <ArrowRight size={12} />
              </Link>
            </div>
          </div>
          <div className="card" id="updates">
            <div className="ch">
              <h3>Office hours and bootcamp</h3>
              <span className="sp"></span>
            </div>
            <div className="cb" style={{ fontSize: 13 }}>
              <div className="kv ">
                <b>office hour</b>
                <div className="v">Thursdays 11:00 · platform team</div>
                <b>bootcamp</b>
                <div className="v">two days, at registration (step 2) · with your embedded engineer</div>
                <b>escalation</b>
                <div className="v">platform lead</div>
                <b>updates</b>
                <div className="v">
                  what changed this week is on <Link to={ROUTES.discover}>Discover</Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}
