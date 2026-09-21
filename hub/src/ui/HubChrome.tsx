import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { ROUTES } from "../routes";
import { Bell, Layers, Search } from "./icons";

/**
 * The Hub's shared chrome for live screens: the top navigation and the footer.
 * Markup mirrors the artboards' `.hnav` and `.hfoot` blocks so the pixels are
 * the same, with real links and buttons in place of the artboards' spans
 * (styled identically by `ui-core.controls.css`).
 */
export type Area = "Discover" | "My workspace" | "Build" | "Learn";

const LINKS: Array<{ label: Area; to: string }> = [
  { label: "Discover", to: ROUTES.discover },
  { label: "My workspace", to: ROUTES.workspace },
  { label: "Build", to: ROUTES.intake },
  { label: "Learn", to: ROUTES.learn },
];

export function HubNav({ active, onSearch }: { active: Area; onSearch?: () => void }) {
  const { principal, signOut } = useAuth();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !menuRef.current?.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [menu]);

  return (
    <div className="hnav">
      <div className="brand">
        <span className="mark">
          <Layers />
        </span>
        <div className="name">
          CrossRiver<small>AI Hub</small>
        </div>
      </div>
      <nav className="links" aria-label="Hub areas">
        {LINKS.map((l) => (
          <Link key={l.label} to={l.to} className={l.label === active ? "on" : ""} aria-current={l.label === active ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
      </nav>
      <span className="sp"></span>
      <button type="button" className="cmd" onClick={onSearch ?? (() => navigate(ROUTES.discover))} aria-label="Search assistants, tools and knowledge (⌘K)">
        <Search size={14} />
        <span>Search assistants, tools, knowledge…</span>
        <span className="kbd">⌘K</span>
      </button>
      <button type="button" className="ibtn" aria-label="Notifications" onClick={() => navigate(ROUTES.workspace)}>
        <Bell />
      </button>
      <div ref={menuRef} style={{ position: "relative", display: "flex" }}>
        <button
          type="button"
          className="av "
          aria-haspopup="menu"
          aria-expanded={menu}
          aria-label={`Account: ${principal?.name ?? ""}`}
          onClick={() => setMenu((m) => !m)}
        >
          {principal?.initials ?? "··"}
        </button>
        {menu && (
          <div
            role="menu"
            tabIndex={-1}
            className="card"
            ref={(el) => el?.querySelector<HTMLElement>("[role=menuitem]")?.focus()}
            onKeyDown={(e) => {
              const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[role=menuitem]"));
              const i = items.indexOf(document.activeElement as HTMLElement);
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
              } else if (e.key === "Escape") {
                e.preventDefault();
                setMenu(false);
                menuRef.current?.querySelector<HTMLElement>("button")?.focus();
              }
            }}
            style={{ position: "absolute", right: 0, top: 36, width: 240, zIndex: 20, boxShadow: "var(--shadow-2)" }}
          >
            <div className="cb" style={{ gap: 2 }}>
              <b style={{ fontSize: 13 }}>{principal?.name}</b>
              <span className="muted" style={{ fontSize: 12 }}>
                {principal?.email}
              </span>
              <span className="muted mono" style={{ fontSize: 11 }}>
                {principal?.roles.join(" · ") || "employee"} · ladder {principal?.ladder}
              </span>
            </div>
            <div className="cf" style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
              <button
                type="button"
                role="menuitem"
                className="btn g s"
                style={{ justifyContent: "flex-start" }}
                onClick={() => {
                  setMenu(false);
                  navigate(ROUTES.settings);
                }}
              >
                Settings
              </button>
              <button
                type="button"
                role="menuitem"
                className="btn g s"
                style={{ justifyContent: "flex-start" }}
                onClick={() => {
                  setMenu(false);
                  void signOut();
                }}
              >
                Sign out
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function HubFoot() {
  return (
    <div className="hfoot">
      <span>Everything in the Hub runs on the platform: one identity chain, one policy bundle, one audit trail.</span>
      <span className="sp"></span>
      <span>Office hour Thursdays 11:00 · escalation: platform lead</span>
    </div>
  );
}

/** Breadcrumb row as the artboards draw it: `Build / Intake brief`. */
export function Crumbs({ area, page }: { area: string; page: string }) {
  return (
    <div className="row muted" style={{ fontSize: "13px" }}>
      <span>{area}</span>
      <span>/</span>
      <b style={{ color: "var(--ink)" }}>{page}</b>
    </div>
  );
}
