import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../api";
import type { Preferences, Principal } from "../../api/types";
import { useAuth, usePrincipal } from "../../auth/AuthProvider";
import { primaryRole } from "../../auth/permits";
import { env } from "../../config/env";
import { track } from "../../telemetry";
import { Field, Seg } from "../../ui/fields";
import { Crumbs, HubFoot, HubNav } from "../../ui/HubChrome";
import { PageState } from "../../ui/PageState";
import { usePalette } from "../../ui/CommandPalette";
import { useToast } from "../../ui/Toast";
import { useTitle } from "../../ui/useTitle";

const LOCALES = [
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "es-US", label: "Español (US)" },
];

/**
 * Settings: the person's preferences, applied at once and saved to the
 * platform (`PUT /me/preferences`), and a read-only view of who the platform
 * says they are. Roles, ladder and entitlements are not editable here; they
 * come from the identity service and the policy bundle (PLT-ID-1).
 */
export default function Settings() {
  const p = usePrincipal();
  const { signOut } = useAuth();
  const palette = usePalette();
  const toast = useToast();
  const qc = useQueryClient();
  useTitle("Settings");
  const [prefs, setPrefs] = useState<Preferences>(p.preferences);
  useEffect(() => {
    setPrefs(p.preferences);
  }, [p.preferences]);

  const save = useMutation({
    mutationFn: (next: Preferences) => api.me.updatePreferences(next),
    onMutate: async (next) => {
      // Apply at once; the ThemeProvider reads preferences from the cached principal.
      await qc.cancelQueries({ queryKey: ["me"] });
      const prev = qc.getQueryData<Principal>(["me"]);
      qc.setQueryData<Principal>(["me"], (me) => (me ? { ...me, preferences: next } : me));
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["me"], ctx.prev);
      toast.notify("crit", "Your preferences could not be saved.", "They are kept for this session only.");
    },
    onSuccess: (me) => {
      qc.setQueryData(["me"], me);
      track("settings.saved");
    },
  });

  const update = (patch: Partial<Preferences>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    save.mutate(next);
  };
  const updateNotif = (key: keyof Preferences["notifications"], on: boolean) => update({ notifications: { ...prefs.notifications, [key]: on } });

  if (!p) return <PageState kind="loading" text="Loading…" />;

  return (
    <div className="hub" data-live style={{ minHeight: "900px" }}>
      <HubNav active="My workspace" onSearch={palette.open} />
      <div className="hwrap">
        <Crumbs area="My workspace" page="Settings" />
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "600", letterSpacing: "-.02em" }}>Settings</h1>
            <div className="muted" style={{ fontSize: "14px", marginTop: "4px" }}>
              Preferences apply at once and travel with your account. Roles and access come from the platform, not from here.
            </div>
          </div>
          <span className="sp"></span>
          <span className={`chip ${save.isPending ? "line busy" : save.isError ? "crit" : "line"}`} role="status">
            {save.isPending ? "saving…" : save.isError ? "not saved" : "saved"}
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 400px", gap: "24px", minHeight: "0" }}>
          <div className="col" style={{ gap: "16px", minWidth: "0" }}>
            <div className="card">
              <div className="ch">
                <h3>Appearance</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ gap: 18 }}>
                <Field label="Theme" help="Light by default (PD-UX-4); dark available. System follows your operating system.">
                  <Seg
                    label="Theme"
                    value={prefs.theme}
                    onChange={(theme) => update({ theme })}
                    options={[
                      { value: "system", label: "System" },
                      { value: "light", label: "Light" },
                      { value: "dark", label: "Dark" },
                    ]}
                  />
                </Field>
                <Field label="Density" help="Dense tightens spacing in cards and tables for long sessions.">
                  <Seg
                    label="Density"
                    value={prefs.density}
                    onChange={(density) => update({ density })}
                    options={[
                      { value: "comfortable", label: "Comfortable" },
                      { value: "dense", label: "Dense" },
                    ]}
                  />
                </Field>
                <Field label="Language" id="locale" help="Interface language and number formats. Assistant answers follow the source language of the material.">
                  <div className="inp" style={{ width: 260 }}>
                    <select id="locale" className="ctl" value={prefs.locale} onChange={(e) => update({ locale: e.target.value })}>
                      {LOCALES.map((l) => (
                        <option key={l.value} value={l.value}>
                          {l.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </Field>
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>Accessibility and assistance</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ gap: 14 }}>
                <Toggle
                  id="a11y"
                  checked={prefs.accessibility}
                  onChange={(accessibility) => update({ accessibility })}
                  title="I use assistive technology"
                  note="Stronger focus rings, underlined links, and unsupported claims spelled out. Carried as an entitlement on every channel (PLT-UI-15), so an assistant adapts its answers too."
                />
                <Toggle
                  id="noai"
                  checked={prefs.noAssistant}
                  onChange={(noAssistant) => update({ noAssistant })}
                  title="Prefer a person over an assistant"
                  note="Where a service offers both, route me to a person by default (PLT-CH-18). Assistants stay available if you open one yourself."
                />
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>Notifications</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ gap: 14 }}>
                <Toggle
                  id="n-req"
                  checked={prefs.notifications.requests}
                  onChange={(on) => updateNotif("requests", on)}
                  title="Access and ladder requests"
                  note="When a request you made is granted, declined, or needs more from you."
                />
                <Toggle
                  id="n-brief"
                  checked={prefs.notifications.briefs}
                  onChange={(on) => updateNotif("briefs", on)}
                  title="Briefs and onboarding"
                  note="Road confirmed, registered, sandbox and staging gates, monthly review due."
                />
                <Toggle
                  id="n-digest"
                  checked={prefs.notifications.digest}
                  onChange={(on) => updateNotif("digest", on)}
                  title="Weekly digest"
                  note="What changed in the catalog for your role, once a week."
                />
              </div>
            </div>
          </div>
          <div className="col" style={{ gap: "16px" }}>
            <div className="card">
              <div className="ch">
                <h3>Your account</h3>
                <span className="sp"></span>
                <span className="chip mono">{env.VITE_AUTH_MODE === "oidc" ? "SSO" : "mock sign-in"}</span>
              </div>
              <div className="cb">
                <div className="kv ">
                  <b>name</b>
                  <div className="v">{p.name}</div>
                  <b>email</b>
                  <div className="v">{p.email}</div>
                  <b>role</b>
                  <div className="v">
                    {primaryRole(p)}
                    {p.roles.length > 1 ? ` · ${p.roles.filter((r) => r !== primaryRole(p)).join(", ")}` : ""}
                  </div>
                  <b>ladder</b>
                  <div className="v">
                    {p.ladder} <span className="muted">your own ceiling; a consumer's may be lower</span>
                  </div>
                  <b>teams</b>
                  <div className="v">{p.teams.length ? p.teams.map((t) => `${t.name}${t.lead ? " · lead" : ""}`).join(", ") : "none"}</div>
                  <b>cost centre</b>
                  <div className="v">{p.costCentre}</div>
                  <b>tenant</b>
                  <div className="v">
                    <span className="mono">{p.tenant}</span>
                  </div>
                </div>
                <div className="banner" style={{ marginTop: 6 }}>
                  <div>
                    Roles, ladder and entitlements are set by the identity service and the policy bundle. To change them, ask your lead; the Hub never edits
                    them.
                  </div>
                </div>
                <div className="row" style={{ marginTop: 4 }}>
                  <button type="button" className="btn s" onClick={() => void signOut()}>
                    Sign out
                  </button>
                  <span className="muted" style={{ fontSize: 12 }}>
                    ends this session on this device
                  </span>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>Your data</h3>
                <span className="sp"></span>
              </div>
              <div className="cb" style={{ fontSize: 13 }}>
                <p>
                  Conversations with an assistant keep session memory only; nothing is remembered across sessions (PD8). Turns are recorded in the audit trail
                  with the sources used, as every platform call is.
                </p>
                <p className="muted" style={{ fontSize: 12.5 }}>
                  Feedback you give on an answer is a labelled example for the consumer's owner to review; it trains nothing on its own.
                </p>
              </div>
            </div>
            <div className="card">
              <div className="ch">
                <h3>About this build</h3>
                <span className="sp"></span>
              </div>
              <div className="cb">
                <div className="kv ">
                  <b>build</b>
                  <div className="v">
                    <span className="mono">{env.VITE_BUILD_SHA}</span>
                  </div>
                  <b>api</b>
                  <div className="v">
                    <span className="mono">{env.VITE_API_MODE === "mock" ? "in-browser mock" : env.VITE_API_BASE}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <HubFoot />
    </div>
  );
}

function Toggle({ id, checked, onChange, title, note }: { id: string; checked: boolean; onChange: (v: boolean) => void; title: string; note: string }) {
  return (
    <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
      <label className={`tog${checked ? " on" : ""}`} style={{ marginTop: 2 }}>
        <input
          id={id}
          type="checkbox"
          role="switch"
          aria-checked={checked}
          checked={checked}
          aria-describedby={`${id}-note`}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="sr-only">{title}</span>
        <i></i>
      </label>
      <div className="col" style={{ gap: 2 }}>
        <label htmlFor={id} style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
          {title}
        </label>
        <span id={`${id}-note`} className="muted" style={{ fontSize: 12 }}>
          {note}
        </span>
      </div>
    </div>
  );
}
