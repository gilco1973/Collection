import { env } from "../config/env";
import { createMockClient } from "./mock";
import { createOidcClient } from "./oidc";
import type { AuthClient } from "./provider";

/** The identity backend for this deployment, chosen once from configuration. */
export const authClient: AuthClient =
  env.VITE_AUTH_MODE === "oidc"
    ? createOidcClient({
        authority: env.VITE_OIDC_AUTHORITY!,
        clientId: env.VITE_OIDC_CLIENT_ID!,
        redirectUri: env.VITE_OIDC_REDIRECT_URI!,
        postLogoutRedirectUri: env.VITE_OIDC_POST_LOGOUT_URI,
        scope: env.VITE_OIDC_SCOPE,
      })
    : createMockClient();
