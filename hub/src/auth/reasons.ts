/**
 * What to tell the person when the identity provider says no, in plain words.
 *
 * The provider's own codes (`login_required`, `access_denied`, …) and oidc-client-ts's internal
 * messages ("No matching state found in storage") are kept as the `code` for the support line and
 * the telemetry; the `message` is what the sign-in page shows. Pure functions, no provider import:
 * an `ErrorResponse` is recognised by shape so the mapping can be tested without a provider.
 */
export interface Reason {
  message: string;
  /** The provider's error code or the underlying message; never shown as the headline. */
  code?: string;
}

export const SESSION_ENDED = "Your sign-in at the identity provider has ended. Sign in again.";
export const PROVIDER_UNREACHABLE = "The identity provider could not be reached. Try again.";
export const LINK_USED = "This sign-in link was already used. Sign in again.";

/** Codes that mean the provider has no session for this person any more, or will not renew it quietly. */
const ENDED_CODES = new Set(["login_required", "interaction_required", "consent_required", "invalid_grant"]);

interface ProviderError {
  error: string;
  error_description?: string | null;
}

function providerError(e: unknown): ProviderError | undefined {
  if (!e || typeof e !== "object") return undefined;
  const o = e as Record<string, unknown>;
  const isResponse = o.name === "ErrorResponse" || typeof o.error === "string";
  if (!isResponse || typeof o.error !== "string" || !o.error) return undefined;
  return { error: o.error, error_description: typeof o.error_description === "string" ? o.error_description : null };
}

function describeCode(code: string, description?: string | null): Reason {
  if (ENDED_CODES.has(code)) return { message: SESSION_ENDED, code };
  return { message: description?.trim() || `The identity provider refused the sign-in (${code}).`, code };
}

/** A failure from the provider or the network during sign-in, silent renew or sign-out. */
export function describeProviderError(e: unknown): Reason {
  const p = providerError(e);
  if (p) return describeCode(p.error, p.error_description);
  if (e instanceof TypeError) return { message: PROVIDER_UNREACHABLE, code: e.message };
  const message = e instanceof Error ? e.message : String(e ?? "");
  if (!message) return { message: "Sign-in failed." };
  if (/failed to fetch|network|load failed/i.test(message)) return { message: PROVIDER_UNREACHABLE, code: message };
  return { message: `Sign-in failed: ${message}`, code: message };
}

/**
 * A failure while finishing a redirect sign-in on the callback URL. The URL is consulted first: the
 * provider's `error` and `error_description` are the truth when present. Without them, the failure is
 * the client's own: no `state`, or a state no longer in storage, which is what a replayed or
 * bookmarked callback link looks like.
 */
export function describeCallbackError(e: unknown, url: string): Reason {
  let params: URLSearchParams | undefined;
  try {
    params = new URL(url).searchParams;
  } catch {
    params = undefined;
  }
  const code = params?.get("error");
  if (code) return describeCode(code, params?.get("error_description"));
  const message = e instanceof Error ? e.message : String(e ?? "");
  if (!params?.has("state") || /\bstate\b/i.test(message)) return { message: LINK_USED, code: message || "no state" };
  return describeProviderError(e);
}
