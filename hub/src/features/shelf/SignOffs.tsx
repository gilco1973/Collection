import { useState } from "react";
import { Link } from "react-router-dom";
import type { ShelfEntry, ShelfRole } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { ROUTES } from "../../routes";
import { Seg } from "../../ui/fields";
import { Crumbs, HubFoot, HubNav } from "../../ui/HubChrome";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useTitle } from "../../ui/useTitle";
import { SignoffForm } from "./SignoffForm";
import { ROLE_LABEL, counts, openRolesFor, signoffView } from "./stages";
import { downloadJson, useShelf } from "./useShelf";
import { api } from "../../api";

type Filter = "all" | "mine" | "recorded" | "open";

/**
 * The sign-off queue: every component of the collection, its version and
 * both sign-offs, who may sign what, and the export that carries what was
 * recorded here into the manifests.
 */
export default function SignOffs() {
  const palette = usePalette();
  const { principal } = useAuth();
  const q = useShelf();
  const [filter, setFilter] = useState<Filter>("all");
  const [openRow, setOpenRow] = useState<string | undefined>();
  const [exporting, setExporting] = useState(false);
  useTitle("Sign-offs");

  if (q.isPending) return <PageState kind="loading" text="Reading the shelf…" />;
  if (q.error || !q.data) return <PageState kind="error" text="The shelf could not be read." detail={(q.error as Error)?.message} />;
  const all = q.data;
  const c = counts(all);
  const mine = all.filter((e) => openRolesFor(e).length > 0);
  const rows =
    filter === "mine"
      ? mine
      : filter === "recorded"
        ? all.filter((e) => Object.keys(e.recorded).length > 0)
        : filter === "open"
          ? all.filter((e) => e.status === "ready" && !e.signed)
          : all;
  const roles: ShelfRole[] = principal ? (["owner", "ai_security"] as ShelfRole[]).filter((r) => all.some((e) => e.youMaySign.includes(r))) : [];

  const exportNow = async () => {
    setExporting(true);
    try {
      downloadJson("shelf-signoffs.json", await api.shelf.export());
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="hub" data-live style={{ minHeight: "1100px" }}>
      <HubNav active="Build" onSearch={palette.open} />
      <div className="hwrap">
        <Crumbs area="Build" page="Sign-offs" />
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "600", letterSpacing: "-.02em" }}>Component sign-offs</h1>
            <div className="muted" style={{ fontSize: "14px", marginTop: "4px" }}>
              A component reaches the shelf when its owner and an AI security engineer have each signed it at its current version. Sign here; the manifest in
              the repository is the record and the commit is the signature.
            </div>
          </div>
          <span className="sp"></span>
          <span className="chip ok">{c.signed} signed</span>
          <span className="chip warn">{c.awaitingOwner} awaiting owner</span>
          <span className="chip warn">{c.awaitingSecurity} awaiting AI security</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 380px", gap: "24px", minHeight: "0" }}>
          <div className="col" style={{ gap: 16, minWidth: 0 }}>
            <div className="card">
              <div className="ch">
                <h3>The queue</h3>
                <span className="sp"></span>
                <Seg
                  label="Show"
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { value: "all", label: `All ${all.length}` },
                    { value: "open", label: "Open" },
                    { value: "mine", label: `Yours to sign ${mine.length}` },
                    { value: "recorded", label: "Recorded here" },
                  ]}
                />
              </div>
              <div className="cb">
                <table className="t">
                  <thead>
                    <tr>
                      <th>Component</th>
                      <th>Version</th>
                      <th>Stage</th>
                      <th>Owner</th>
                      <th>AI security</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e) => (
                      <Row key={e.name} e={e} open={openRow === e.name} onToggle={() => setOpenRow(openRow === e.name ? undefined : e.name)} />
                    ))}
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={6} className="muted">
                          {filter === "mine" ? "Nothing is waiting on you." : "Nothing here."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div className="col" style={{ gap: 16 }}>
            <div className="card">
              <div className="ch">
                <h3>You</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ fontSize: 13, gap: 8 }}>
                {roles.length === 0 ? (
                  <div className="muted">
                    You sign nothing yet. Owners sign by name (the manifest's <span className="mono">owner</span> is their handle); AI security engineers sign
                    by the <span className="mono">ai.security</span> role, granted by the security team lead.{" "}
                    <Link to={ROUTES.shelfOnboarding}>How to become either</Link>
                  </div>
                ) : (
                  <>
                    <div>
                      You may sign as <b>{roles.map((r) => ROLE_LABEL[r].toLowerCase()).join(" and ")}</b>
                      {roles.includes("owner") ? " on the components that name you" : ""}.
                    </div>
                    <div className="muted">
                      {mine.length} waiting on you. Before you sign: run the tests and the live example, read the walkthrough and the rules. The form asks you
                      to attest to each.
                    </div>
                  </>
                )}
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>Into the repository</h3>
                <span className="sp"></span>
                <span className={`chip ${c.recorded ? "warn" : "line"}`}>{c.recorded} recorded here</span>
              </div>
              <div className="cb" style={{ fontSize: 13, gap: 10 }}>
                <div>
                  A sign-off recorded here is a request until it is in the manifest. Export the queue, apply it, and commit; the shelf tool re-runs the tests
                  before it writes anything.
                </div>
                <pre className="mono" style={{ fontSize: 12, margin: 0, whiteSpace: "pre-wrap" }}>
                  {
                    'python3 tools/shelf.py --apply-signoffs shelf-signoffs.json\npython3 tools/shelf.py --write\ngit commit -am "Sign off <component> <version>"'
                  }
                </pre>
                <div className="row">
                  <button type="button" className={`btn p${c.recorded && !exporting ? "" : " dis"}`} disabled={!c.recorded || exporting} onClick={exportNow}>
                    {exporting ? "Preparing…" : "Download shelf-signoffs.json"}
                  </button>
                  <Link to={ROUTES.shelfOnboarding} className="btn g">
                    The onboarding process
                  </Link>
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

function Row({ e, open, onToggle }: { e: ShelfEntry; open: boolean; onToggle: () => void }) {
  const owner = signoffView(e, "owner");
  const sec = signoffView(e, "ai_security");
  const mayOpen = openRolesFor(e).length > 0;
  return (
    <>
      <tr>
        <td>
          <Link to={e.hubPath}>{e.title}</Link>
          <div className="muted" style={{ fontSize: 12 }}>
            {e.kind} · {e.language} · owner {e.owner}
          </div>
        </td>
        <td>
          <span className="mono">{e.version}</span>
        </td>
        <td>
          <span className={`chip ${e.stage.label === "on the shelf" ? "ok" : e.status === "deprecated" ? "crit" : "line"}`}>{e.stage.label}</span>
        </td>
        <td>
          <span className={`chip ${owner.chip}`} title={owner.text}>
            {owner.kind}
          </span>
        </td>
        <td>
          <span className={`chip ${sec.chip}`} title={sec.text}>
            {sec.kind}
          </span>
        </td>
        <td>
          {mayOpen && (
            <button type="button" className="btn g s" onClick={onToggle} aria-expanded={open}>
              {open ? "Close" : "Sign"}
            </button>
          )}
        </td>
      </tr>
      {open && mayOpen && (
        <tr>
          <td colSpan={6} style={{ background: "var(--surface-2)" }}>
            <div style={{ maxWidth: 640, padding: "8px 4px" }}>
              <SignoffForm entry={e} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
