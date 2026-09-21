import { useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useAuth, type SignInState } from "../auth/AuthProvider";
import { env } from "../config/env";

/**
 * Sign-in. With a real IdP this page has one button that redirects; in mock
 * mode it offers the dev personas so a reviewer can see each role's Hub.
 */
export default function SignIn() {
  const { signIn, personas, snapshot } = useAuth();
  const [params] = useSearchParams();
  const location = useLocation();
  const returnTo = params.get("returnTo") ?? "/discover";
  // A failure on this page (the provider unreachable, a refused callback) is the freshest word; otherwise the
  // reason the guard sent us here with, then whatever the provider last said.
  const sent = (location.state as SignInState | null) ?? undefined;
  const fresh = snapshot.status === "error" ? snapshot : undefined;
  const reason = fresh?.error ?? sent?.reason ?? snapshot.error;
  const detail = fresh?.detail ?? (sent?.reason ? sent.detail : snapshot.detail);
  const [busy, setBusy] = useState<string | null>(null);

  const go = async (persona?: string) => {
    setBusy(persona ?? "sso");
    try {
      await signIn({ returnTo, persona });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="hub" style={{ minHeight: 900 }}>
      <div className="hwrap" style={{ maxWidth: 520, paddingTop: 96 }}>
        <div className="brand" style={{ padding: 0, marginBottom: 20 }}>
          <span className="mark">
            <svg
              className="i "
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M8 2 2 5l6 3 6-3zM2 8l6 3 6-3M2 11l6 3 6-3" />
            </svg>
          </span>
          <div className="name">
            CrossRiver<small>AI Hub</small>
          </div>
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-.02em" }}>Sign in</h1>
        <p className="muted" style={{ fontSize: 14, marginTop: 6, marginBottom: 18 }}>
          Use your bank account. What you can see and do here follows your role and channel; nothing is a side door.
        </p>
        {reason && (
          <div className="banner warn" role="status" style={{ marginBottom: 14 }}>
            <div className="col" style={{ gap: 4 }}>
              <span>{reason}</span>
              {detail && detail !== reason && (
                <span className="mono" style={{ fontSize: 11.5 }} data-signin-detail>
                  {detail}
                </span>
              )}
            </div>
          </div>
        )}

        {env.VITE_AUTH_MODE === "oidc" || !personas ? (
          <button type="button" className="btn p" onClick={() => go()} disabled={busy !== null} id="signin-sso">
            Continue with CrossRiver sign-in
          </button>
        ) : (
          <div className="card">
            <div className="ch">
              <h3>Development personas</h3>
              <span className="sp"></span>
              <span className="chip warn">mock identity</span>
            </div>
            <div className="cb" style={{ gap: 6 }}>
              {personas.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  id={`persona-${p.id}`}
                  className="radio"
                  style={{ width: "100%", textAlign: "left" }}
                  onClick={() => go(p.id)}
                  disabled={busy !== null}
                  aria-busy={busy === p.id}
                >
                  <span className="av">
                    {p.label
                      .split(" ")
                      .map((w) => w[0])
                      .join("")
                      .slice(0, 2)
                      .toUpperCase()}
                  </span>
                  <div className="col" style={{ gap: 0 }}>
                    <b style={{ fontSize: 13 }}>{p.label}</b>
                    <span className="muted" style={{ fontSize: 11.5 }}>
                      {p.description}
                    </span>
                  </div>
                </button>
              ))}
            </div>
            <div className="cf">
              <span>Set VITE_AUTH_MODE=oidc to use the bank identity provider.</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
