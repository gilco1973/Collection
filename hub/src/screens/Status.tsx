import { Link } from "react-router-dom";
import { ApiError } from "../api/errors";
import { useAuth } from "../auth/AuthProvider";
import { ROUTES } from "../routes";

export function Forbidden() {
  const { principal, principalError, signOut } = useAuth();
  // The platform refused the person themselves (403 on /me): say why in the platform's words, with the request id
  // the identity team will ask for. Otherwise a role did not allow a listing or an action.
  const refused = !principal && principalError instanceof ApiError && principalError.status === 403 ? principalError : undefined;
  return (
    <div className="hub" style={{ minHeight: 600 }}>
      <div className="hwrap" style={{ paddingTop: 80, maxWidth: 640 }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-.02em" }}>{refused?.problem?.title ?? "Your role does not allow this"}</h1>
        {refused ? (
          <>
            <p className="muted" style={{ fontSize: 14, marginTop: 6 }}>
              {refused.message}
            </p>
            <p className="muted mono" style={{ fontSize: 12, marginTop: 6 }}>
              {refused.supportLine}
            </p>
          </>
        ) : (
          <p className="muted" style={{ fontSize: 14, marginTop: 6 }}>
            {principal ? `You are signed in as ${principal.name} (${principal.roles.join(", ") || "employee"}).` : ""} Access to a listing or an action is
            granted by role and channel through the policy bundle. What you cannot see, you can request from its listing.
          </p>
        )}
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
