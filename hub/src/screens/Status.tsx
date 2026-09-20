import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { ROUTES } from "../routes";

export function Forbidden() {
  const { principal, signOut } = useAuth();
  return (
    <div className="hub" style={{ minHeight: 600 }}>
      <div className="hwrap" style={{ paddingTop: 80, maxWidth: 640 }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-.02em" }}>Your role does not allow this</h1>
        <p className="muted" style={{ fontSize: 14, marginTop: 6 }}>
          {principal ? `You are signed in as ${principal.name} (${principal.roles.join(", ") || "employee"}).` : ""} Access to a listing or an action is granted
          by role and channel through the policy bundle. What you cannot see, you can request from its listing.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <Link className="btn p" to={ROUTES.discover}>
            Back to Discover
          </Link>
          <button type="button" className="btn g" onClick={() => void signOut()}>
            Sign in as someone else
          </button>
        </div>
      </div>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="hub" style={{ minHeight: 600 }}>
      <div className="hwrap" style={{ paddingTop: 80, maxWidth: 640 }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-.02em" }}>Nothing here</h1>
        <p className="muted" style={{ fontSize: 14, marginTop: 6 }}>
          That page does not exist, or it belongs to something you cannot see.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <Link className="btn p" to={ROUTES.discover}>
            Back to Discover
          </Link>
        </div>
      </div>
    </div>
  );
}
