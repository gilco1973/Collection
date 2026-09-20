import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import type { Action, Resource } from "./permits";

/**
 * Route guard. Waits for the token, then for the platform's principal, then
 * renders. Signed-out people go to /signin with a return path; a principal the
 * platform refuses (403 on /me) sees the forbidden page.
 */
/** Replace with your own page states; these keep the guard free of any UI dependency. */
export const defaultStates = {
  loading: (text: string) => <p role="status">{text}</p>,
  error: (text: string, detail?: string) => (
    <p role="alert">
      {text} {detail}
    </p>
  ),
};

export function RequireAuth({
  children,
  action,
  resource,
  isForbidden = (e) => (e as { status?: number }).status === 403,
  states = defaultStates,
}: {
  children: ReactNode;
  action?: Action;
  resource?: Resource;
  /** How to recognise a 403 from GET /me (typed-api-client's ForbiddenError has status 403). */
  isForbidden?: (e: Error) => boolean;
  states?: typeof defaultStates;
}) {
  const { snapshot, principal, principalError, can } = useAuth();
  const location = useLocation();

  if (snapshot.status === "loading" || snapshot.status === "signing-in") {
    return states.loading("Signing you in…");
  }
  if (snapshot.status === "signed-out" || snapshot.status === "error") {
    const returnTo = `${location.pathname}${location.search}`;
    return <Navigate to={`/signin?returnTo=${encodeURIComponent(returnTo)}`} replace state={{ reason: snapshot.error }} />;
  }
  if (principalError) {
    if (isForbidden(principalError)) return <Navigate to="/403" replace />;
    return states.error("The platform could not resolve your account.", principalError.message);
  }
  if (!principal) return states.loading("Loading your workspace…");
  if (action && !can(action, resource)) return <Navigate to="/403" replace />;
  return <>{children}</>;
}
