import { InMemoryWebStorage, UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import type { AuthClient } from "./provider";
import { describeProviderError } from "./reasons";
import type { AuthSnapshot } from "./types";

export interface OidcConfig {
  authority: string;
  clientId: string;
  redirectUri: string;
  postLogoutRedirectUri?: string;
  scope: string;
}

/**
 * Authorization Code + PKCE against the bank's identity provider (IdentityServer,
 * Auth0, or any OpenID Connect issuer with discovery).
 *
 * Enterprise choices made here:
 * - Tokens live in memory only (`InMemoryWebStorage`), never in localStorage,
 *   so an XSS cannot lift a token out of storage. A page reload therefore
 *   re-establishes the session through silent renew (the IdP's session cookie),
 *   not from a persisted token.
 * - `response_type=code` with PKCE; no implicit flow.
 * - Silent renew is automatic; expiry and remote sign-out propagate to the app.
 * - The platform, not the client, decides what the person may do: the token
 *   only proves who they are, and `GET /me` resolves the principal.
 */
export function createOidcClient(cfg: OidcConfig): AuthClient {
  const manager = new UserManager({
    authority: cfg.authority,
    client_id: cfg.clientId,
    redirect_uri: cfg.redirectUri,
    post_logout_redirect_uri: cfg.postLogoutRedirectUri ?? window.location.origin,
    scope: cfg.scope,
    response_type: "code",
    automaticSilentRenew: true,
    loadUserInfo: true,
    monitorSession: true,
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    // Sign-in state (PKCE verifier, nonce) must survive the redirect; session
    // storage is scoped to the tab and cleared when it closes.
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });

  const listeners = new Set<(s: AuthSnapshot) => void>();
  const snapshotOf = (user: User | null | undefined): AuthSnapshot =>
    user && !user.expired
      ? {
          status: "signed-in",
          accessToken: user.access_token,
          subject: { id: user.profile.sub, name: user.profile.name, email: user.profile.email },
        }
      : { status: "signed-out" };
  const emit = (s: AuthSnapshot) => listeners.forEach((l) => l(s));

  manager.events.addUserLoaded((u) => emit(snapshotOf(u)));
  manager.events.addAccessTokenExpired(() => emit({ status: "signed-out", error: "Your session expired." }));
  manager.events.addUserSignedOut(() => {
    void manager.removeUser();
    emit({ status: "signed-out", error: "You were signed out." });
  });
  // A refused renew (`login_required` and its kin) is the provider saying the session is over: say so in
  // plain words and keep the provider's code for the support line.
  manager.events.addSilentRenewError((e) => {
    const reason = describeProviderError(e);
    emit({ status: "error", error: reason.message, detail: reason.code ?? e.message });
  });

  return {
    async initialize() {
      const user = await manager.getUser();
      if (user && !user.expired) return snapshotOf(user);
      try {
        // Reload with no in-memory token: ask the IdP quietly, using its own session.
        const renewed = await manager.signinSilent();
        return snapshotOf(renewed);
      } catch {
        return { status: "signed-out" };
      }
    },
    async signIn(opts) {
      await manager.signinRedirect({ state: { returnTo: opts?.returnTo ?? "/" } });
    },
    async completeSignIn() {
      const user = await manager.signinCallback();
      const returnTo = (user?.state as { returnTo?: string } | undefined)?.returnTo;
      return { snapshot: snapshotOf(user), returnTo };
    },
    async signOut() {
      // A provider without an end-session endpoint (or one whose discovery cannot be read right now)
      // cannot be told; the person is still signed out of the hub, here and now.
      const endSession = await manager.metadataService.getEndSessionEndpoint().catch(() => undefined);
      if (!endSession) {
        await manager.removeUser();
        emit({ status: "signed-out" });
        return;
      }
      await manager.signoutRedirect();
    },
    async getAccessToken() {
      const user = await manager.getUser();
      if (user && !user.expired) return user.access_token;
      try {
        const renewed = await manager.signinSilent();
        return renewed?.access_token;
      } catch {
        return undefined;
      }
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    isCallbackUrl() {
      const here = new URL(window.location.href);
      const cb = new URL(cfg.redirectUri);
      return here.pathname === cb.pathname && (here.searchParams.has("code") || here.searchParams.has("error"));
    },
  };
}
