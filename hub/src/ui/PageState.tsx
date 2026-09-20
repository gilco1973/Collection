/** Full-page loading, empty and error states on the Hub chrome. */
export function PageState({ kind, text, detail, action }: { kind: "loading" | "error" | "empty"; text: string; detail?: string; action?: React.ReactNode }) {
  return (
    <div className="hub" data-loading={kind === "loading" ? "true" : undefined} style={{ minHeight: 420 }}>
      <div className="hwrap" style={{ paddingTop: 80 }}>
        <div className={`banner ${kind === "error" ? "crit" : ""}`} role={kind === "error" ? "alert" : "status"} aria-busy={kind === "loading"}>
          <div className="col" style={{ gap: 4, flex: 1 }}>
            <b>{text}</b>
            {detail && <span style={{ fontSize: 12.5 }}>{detail}</span>}
            {action && (
              <div className="row" style={{ marginTop: 6 }}>
                {action}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
