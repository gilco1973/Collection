import type { AuthSnapshot, MockPersona } from "./types";

/**
 * The contract every identity backend satisfies. `AuthProvider` (React) talks
 * only to this, so switching the bank's IdP, or running against mock personas
 * in a demo, changes one factory call in `auth/index.ts`.
 */
export interface AuthClient {
  /** Restore an existing session (page reload, silent renew) and report its state. */
  initialize(): Promise<AuthSnapshot>;
  /** Start sign-in. For OIDC this redirects; for mock it resolves with a signed-in snapshot. */
  signIn(opts?: { returnTo?: string; persona?: string }): Promise<AuthSnapshot | void>;
  /** Finish a redirect-based sign-in when the app boots on the callback route. */
  completeSignIn(): Promise<{ snapshot: AuthSnapshot; returnTo?: string }>;
  signOut(): Promise<void>;
  /** A current bearer token, refreshing if needed; undefined when signed out. */
  getAccessToken(): Promise<string | undefined>;
  /** Subscribe to state changes (token renewed, session expired, signed out elsewhere). */
  subscribe(listener: (s: AuthSnapshot) => void): () => void;
  /** Mock only: the personas a developer can pick. */
  personas?(): MockPersona[];
  /** True when the current URL is this provider's sign-in callback. */
  isCallbackUrl(): boolean;
}
