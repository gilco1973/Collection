import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, onUnauthorized } from "../api";
import { track } from "../telemetry";
import { authClient } from "./client";
import { permits, type Action, type Resource } from "./permits";
import type { AuthSnapshot, MockPersona, Principal } from "./types";

interface AuthContextValue {
  snapshot: AuthSnapshot;
  /** The platform's view of the signed-in person; undefined until `GET /me` resolves. */
  principal: Principal | undefined;
  principalError: Error | null;
  signIn: (opts?: { returnTo?: string; persona?: string }) => Promise<void>;
  signOut: () => Promise<void>;
  personas: MockPersona[] | undefined;
  can: (action: Action, resource?: Resource) => boolean;
}

const Ctx = createContext<AuthContextValue | null>(null);

export const CALLBACK_PATH = "/auth/callback";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<AuthSnapshot>({ status: "loading" });
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // Boot: finish a redirect sign-in if this is the callback, else restore.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (authClient.isCallbackUrl()) {
          const { snapshot: s, returnTo } = await authClient.completeSignIn();
          if (cancelled) return;
          // A silent-renew frame: the client has handed the result to the page that opened it; render nothing here.
          if (window.self !== window.top) return;
          setSnapshot(s);
          navigate(returnTo ?? "/", { replace: true });
          track("auth.signed_in", { mode: "redirect" });
          return;
        }
        // Dev and e2e convenience in mock mode: `?mockPersona=gk` signs in without the picker.
        const persona = new URLSearchParams(location.search).get("mockPersona");
        if (persona && authClient.personas) {
          const s = await authClient.signIn({ persona });
          if (!cancelled && s) setSnapshot(s);
          return;
        }
        const s = await authClient.initialize();
        if (!cancelled) setSnapshot(s);
      } catch (e) {
        if (!cancelled) setSnapshot({ status: "error", error: (e as Error).message });
      }
    })();
    return () => {
      cancelled = true;
    };
    // Boot once; later changes arrive through subscribe().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () =>
      authClient.subscribe((s) => {
        setSnapshot(s);
        if (s.status === "signed-out") queryClient.clear();
      }),
    [queryClient],
  );

  // A 401 from the API means the token the provider gave us is no longer good.
  useEffect(() => {
    onUnauthorized(() => {
      setSnapshot({ status: "signed-out", error: "Your session has ended. Sign in again to continue." });
      queryClient.clear();
    });
  }, [queryClient]);

  const signedIn = snapshot.status === "signed-in";
  const me = useQuery({
    queryKey: ["me"],
    queryFn: ({ signal }) => api.me.get(signal),
    enabled: signedIn,
    staleTime: 5 * 60_000,
  });

  const signIn = useCallback(
    async (opts?: { returnTo?: string; persona?: string }) => {
      setSnapshot((s) => ({ ...s, status: "signing-in" }));
      const s = await authClient.signIn(opts);
      if (s) {
        setSnapshot(s);
        track("auth.signed_in", { mode: "mock" });
        navigate(opts?.returnTo ?? "/", { replace: true });
      }
    },
    [navigate],
  );

  const signOut = useCallback(async () => {
    track("auth.signed_out");
    queryClient.clear();
    await authClient.signOut();
    setSnapshot({ status: "signed-out" });
    navigate("/signin", { replace: true });
  }, [navigate, queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      snapshot,
      principal: me.data,
      principalError: me.error,
      signIn,
      signOut,
      personas: authClient.personas?.(),
      can: (action, resource) => permits(me.data, action, resource),
    }),
    [snapshot, me.data, me.error, signIn, signOut],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

/** The signed-in principal, or throws: use only under RequireAuth. */
export function usePrincipal(): Principal {
  const { principal } = useAuth();
  if (!principal) throw new Error("usePrincipal before the principal resolved; render under RequireAuth");
  return principal;
}
