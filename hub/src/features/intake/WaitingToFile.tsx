import { Link } from "react-router-dom";
import type { Brief } from "../../api/types";
import { ROUTES } from "../../routes";
import { ArrowRight } from "../../ui/icons";

/**
 * The briefs in a lead's list that are not their own: the team's drafts, which the platform lets the lead of the
 * team open and file (a write profile is filed by the lead). Rendered only when there are some, below the page's
 * own content, so the artboards' screens are unchanged.
 */
export function briefsWaitingFor(briefs: Brief[] | undefined, principalId: string): Brief[] {
  return (briefs ?? [])
    .filter((b) => b.createdBy !== principalId && (b.status === "draft" || b.status === "needs_info"))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

const STATUS_TEXT: Record<string, string> = { draft: "draft", needs_info: "needs info" };

export function WaitingToFile({ briefs, teams }: { briefs: Brief[]; teams: Array<{ id: string; name: string }> }) {
  if (briefs.length === 0) return null;
  const teamName = (id: string) => teams.find((t) => t.id === id)?.name ?? id;
  return (
    <div className="card" data-testid="waiting-to-file" data-guide="intake-waiting">
      <div className="ch">
        <h3>Waiting for you to file</h3>
        <span className="sp"></span>
        <span className="chip ink">{briefs.length}</span>
      </div>
      <div className="cb">
        <span className="muted" style={{ fontSize: 13 }}>
          Drafts from your team. A write profile (W1 or W2) is filed by the team lead; open one, review it, and file it from its last section.
        </span>
        {briefs.map((b) => (
          <div key={b.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--rule)" }}>
            <div className="col" style={{ gap: "1px", flex: "1" }}>
              <b>{b.content.useCase.name || "Untitled brief"}</b>
              <span className="muted" style={{ fontSize: "12px" }}>
                {`${teamName(b.content.useCase.teamId)} · ${b.content.people.productOwner || b.createdBy} · updated ${b.updatedAt.slice(0, 10)}`}
              </span>
            </div>
            <span className={`chip ${b.content.dataAndTools.tierCeiling === "R" ? "" : "warn"}`}>{`ceiling ${b.content.dataAndTools.tierCeiling}`}</span>
            <span className="chip line">{STATUS_TEXT[b.status] ?? b.status}</span>
            <Link className="btn s" to={`${ROUTES.intake}/${b.id}`}>
              Open
              <ArrowRight size={14} />
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
