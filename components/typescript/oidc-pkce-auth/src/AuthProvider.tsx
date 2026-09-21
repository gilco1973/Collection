import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { permits, type Action, type Resource } from "./permits";
import type { AuthClient } from "./provider";
import type { AuthSnapshot, MockPersona, Principal } from "./types";

/**
 * The token lifecycle (from the `AuthClient`) and the principal (from `GET /me`, the platform's authority on
 * roles, ladder and entitlements), as one React context. Everything this component talks to is injected:
 * the auth client, the call that fetches the principal, a hook that fires when the API answered 401, and a
 * telemetry sink; so the same provider serves the OIDC client in production and the persona picker in tests.
 */
export interface AuthDeps {
  client: AuthClient;
  /** `GET /me` with the current bearer; typed-api-client's `api.me.get` fits. */
  fetchPrincipal: (signal?: AbortSignal) => Promise<Principal>;
  /** Subscribe to the API client's 401 hook; return nothing or an unsubscribe. */
  onUnauthorized?: (handler: () => void) => void | (() => void);
  track?: (event: string, data?: Record<string, unknown>) => void;
  /** Where sign-in lands when no return path is known. */
  home?: string;
}

interface AuthContextValue {
  snapshot: AuthSnapshot;
  principal: Principal | undefined;
  principalError: Error | null;
  signIn: (opts?: { returnTo?: string; persona?: string }) => Promise<void>;
  signOut: () => Promise<void>;
  personas: MockPersona[] | undefined;
  can: (action: Action, resource?: Resource) => boolean;
}

const Ctx = createContext<AuthContextValue | null>(null);

export const CALLBACK_PATH = "/auth/callback";

export function AuthProvider({ deps, children }: { deps: AuthDeps; children: ReactNode }) {
  const { client, fetchPrincipal, onUnauthorized, track = () => {}, home = "/" } = deps;
  const [snapshot, setSnapshot] = useState<AuthSnapshot>({ status: "loading" });
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // Boot: finish a redirect sign-in if this is the callback, else restore.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (client.isCallbackUrl()) {
          const { snapshot: s, returnTo } = await client.completeSignIn();
          if (cancelled) return;
          setSnapshot(s);
          navigate(returnTo ?? home, { replace: true });
          track("auth.signed_in", { mode: "redirect" });
          return;
        }
        // Dev and e2e convenience in mock mode: `?mockPersona=gk` signs in without the picker.
        const persona = new URLSearchParams(location.search).get("mockPersona");
        if (persona && client.personas) {
          const s = await client.signIn({ persona });
          if (!cancelled && s) setSnapshot(s);
          return;
        }
        const s = await client.initialize();
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
      client.subscribe((s) => {
        setSnapshot(s);
        if (s.status === "signed-out") queryClient.clear();
      }),
    [client, queryClient],
  );

  // A 401 from the API means the token the provider gave us is no longer good.
  useEffect(() => {
    const off = onUnauthorized?.(() => {
      setSnapshot({ status: "signed-out", error: "Your session has ended. Sign in again to continue." });
      queryClient.clear();
    });
    return typeof off === "function" ? off : undefined;
  }, [onUnauthorized, queryClient]);

  const signedIn = snapshot.status === "signed-in";
  const me = useQuery({ queryKey: ["me"], queryFn: ({ signal }) => fetchPrincipal(signal), enabled: signedIn, staleTime: 5 * 60_000, retry: false });

  const signIn = useCallback(
    async (opts?: { returnTo?: string; persona?: string }) => {
      setSnapshot((s) => ({ ...s, status: "signing-in" }));
      let s: Awaited<ReturnType<AuthClient["signIn"]>>;
      try {
        s = await client.signIn(opts);
      } catch (e) {
        // A redirect that never leaves (unreachable discovery document, bad authority) must not leave the app on
        // "Signing you in…" for ever: record the failure so the sign-in page can show it, then let the caller see it.
        setSnapshot({ status: "error", error: (e as Error).message });
        throw e;
      }
      if (s) {
        setSnapshot(s);
        track("auth.signed_in", { mode: "mock" });
        navigate(opts?.returnTo ?? home, { replace: true });
      }
    },
    [client, navigate, track, home],
  );

  const signOut = useCallback(async () => {
    track("auth.signed_out");
    queryClient.clear();
    await client.signOut();
    setSnapshot({ status: "signed-out" });
    navigate("/signin", { replace: true });
  }, [client, navigate, queryClient, track]);

  const value = useMemo<AuthContextValue>(
    () => ({ snapshot, principal: me.data, principalError: me.error, signIn, signOut, personas: client.personas?.(), can: (action, resource) => permits(me.data, action, resource) }),
    [snapshot, me.data, me.error, signIn, signOut, client],
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
