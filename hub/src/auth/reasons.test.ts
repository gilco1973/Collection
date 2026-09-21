import { describe, expect, it } from "vitest";
import { LINK_USED, PROVIDER_UNREACHABLE, SESSION_ENDED, describeCallbackError, describeProviderError } from "./reasons";

/** oidc-client-ts's ErrorResponse, by shape: the mapping never imports the provider. */
function errorResponse(error: string, error_description?: string) {
  const e = new Error(error_description || error) as Error & { error: string; error_description: string | null };
  Object.defineProperty(e, "name", { value: "ErrorResponse" });
  e.error = error;
  e.error_description = error_description ?? null;
  return e;
}

const CB = "https://hub.example/auth/callback";

describe("describeProviderError", () => {
  it("maps a refused silent renew to plain words and keeps the provider's code", () => {
    for (const code of ["login_required", "interaction_required", "consent_required", "invalid_grant"]) {
      expect(describeProviderError(errorResponse(code))).toEqual({ message: SESSION_ENDED, code });
    }
    expect(describeProviderError({ error: "login_required" })).toEqual({ message: SESSION_ENDED, code: "login_required" });
  });
  it("shows the provider's description for any other code, or names the code", () => {
    expect(describeProviderError(errorResponse("access_denied", "The person cancelled"))).toEqual({ message: "The person cancelled", code: "access_denied" });
    expect(describeProviderError(errorResponse("temporarily_unavailable"))).toEqual({ message: "The identity provider refused the sign-in (temporarily_unavailable).", code: "temporarily_unavailable" });
  });
  it("a failed fetch of the discovery document is the provider being unreachable", () => {
    expect(describeProviderError(new TypeError("Failed to fetch"))).toEqual({ message: PROVIDER_UNREACHABLE, code: "Failed to fetch" });
    expect(describeProviderError(new Error("NetworkError when attempting to fetch resource."))).toMatchObject({ message: PROVIDER_UNREACHABLE });
  });
  it("anything else is reported as a failure with its message behind it", () => {
    expect(describeProviderError(new Error("boom"))).toEqual({ message: "Sign-in failed: boom", code: "boom" });
    expect(describeProviderError(undefined)).toEqual({ message: "Sign-in failed." });
  });
});

describe("describeCallbackError", () => {
  it("the provider's own error on the callback URL is the truth", () => {
    expect(describeCallbackError(new Error("whatever"), `${CB}?error=access_denied&error_description=The+person+cancelled&state=abc`)).toEqual({ message: "The person cancelled", code: "access_denied" });
    expect(describeCallbackError(new Error("x"), `${CB}?error=login_required&state=abc`)).toEqual({ message: SESSION_ENDED, code: "login_required" });
    expect(describeCallbackError(new Error("x"), `${CB}?error=server_error&state=abc`)).toEqual({ message: "The identity provider refused the sign-in (server_error).", code: "server_error" });
  });
  it("a callback without state, or whose state is gone, is a used link", () => {
    expect(describeCallbackError(new Error("No state in response"), `${CB}?code=abc`)).toEqual({ message: LINK_USED, code: "No state in response" });
    expect(describeCallbackError(new Error("No matching state found in storage"), `${CB}?code=abc&state=used`)).toEqual({ message: LINK_USED, code: "No matching state found in storage" });
  });
  it("a token endpoint refusal (invalid_grant) on a fresh callback is the session having ended", () => {
    expect(describeCallbackError(errorResponse("invalid_grant", "pkce or client mismatch"), `${CB}?code=abc&state=fresh`)).toEqual({ message: SESSION_ENDED, code: "invalid_grant" });
  });
  it("the provider unreachable at the token endpoint", () => {
    expect(describeCallbackError(new TypeError("Failed to fetch"), `${CB}?code=abc&state=fresh`)).toMatchObject({ message: PROVIDER_UNREACHABLE });
  });
});
