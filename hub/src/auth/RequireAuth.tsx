import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ForbiddenError } from "../api/errors";
import { PageState } from "../ui/PageState";
import { SIGN_IN_PATH, useAuth, type SignInState } from "./AuthProvider";
import type { Action, Resource } from "./permits";

/**
 * Route guard. Waits for the token, then for the platform's principal, then
 * renders. Signed-out people go to /signin with a return path; a principal the
 * platform refuses (403 on /me) sees the forbidden page.
 */
export function RequireAuth({ children, action, resource }: { children: ReactNode; action?: Action; resource?: Resource }) {
  const { snapshot, principal, principalError, can } = useAuth();
  const location = useLocation();

  if (snapshot.status === "loading" || snapshot.status === "signing-in") {
    return <PageState kind="loading" text="Signing you in…" />;
  }
  if (snapshot.status === "signed-out" || snapshot.status === "error") {
    const returnTo = `${location.pathname}${location.search}`;
    const state: SignInState = { reason: snapshot.error, detail: snapshot.detail };
    return <Navigate to={`${SIGN_IN_PATH}?returnTo=${encodeURIComponent(returnTo)}`} replace state={state} />;
  }
  if (principalError) {
    if (principalError instanceof ForbiddenError) return <Navigate to="/403" replace />;
    return <PageState kind="error" text="The platform could not resolve your account." detail={principalError.message} />;
  }
  if (!principal) return <PageState kind="loading" text="Loading your workspace…" />;
  if (action && !can(action, resource)) return <Navigate to="/403" replace />;
  return <>{children}</>;
}

/**
 * The provider's redirect callback, rendered from the auth snapshot: a spinner while the sign-in is
 * being finished, and the sign-in page with the reason as soon as it failed, never a spinner that stays.
 */
export function AuthCallback() {
  const { snapshot } = useAuth();
  if (snapshot.status === "error" || snapshot.status === "signed-out") {
    const state: SignInState = { reason: snapshot.error, detail: snapshot.detail };
    return <Navigate to={SIGN_IN_PATH} replace state={state} />;
  }
  return <PageState kind="loading" text="Finishing sign-in…" />;
}
