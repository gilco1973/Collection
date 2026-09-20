import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { readApiKey, signInUrl, storeApiKey } from "../api/client";
import { useContract, useForgetMe, useMe, useProfile, useSignOut, useSignOutEverywhere, useSignedIn } from "../api/hooks";
import LanguageSwitcher from "../components/LanguageSwitcher";
import PersonaPicker from "../components/PersonaPicker";
import { SuggestionsToggle } from "../components/Nudges";
import { clearNudgeState } from "../nudgeStore";
import { Card, ErrorBox, Loading, btn, btnDanger, btnPrimary, input } from "../components/States";
import { usePageTitle } from "../usePageTitle";

export default function Settings() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const me = useMe();
  const contract = useContract();
  const signOut = useSignOut();
  const signOutEverywhere = useSignOutEverywhere();
  const forget = useForgetMe();
  const profile = useProfile(useSignedIn());
  const [confirmForget, setConfirmForget] = useState(false);
  usePageTitle(t("settings.title"));
  const [stored, setStored] = useState(readApiKey);
  const [key, setKey] = useState(stored);
  const [saved, setSaved] = useState(false);
  const yesNo = (value: boolean) => (value ? t("common.yes") : t("common.no"));
  const save = (value: string) => {
    storeApiKey(value);
    setStored(value);
    setKey(value);
    setSaved(true);
    void client.invalidateQueries();
  };
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{t("settings.title")}</h1>
      <Card title={t("settings.identity")}>
        {me.data && !me.data.sso_configured && <p className="text-sm text-muted">{t("auth.ssoUnavailable")}</p>}
        {me.data?.sso_configured && me.data.user && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span data-testid="settings-user">{t("auth.signedInAs", { name: me.data.user.name })}</span>
              {me.data.user.email && <span className="font-mono text-[12px] text-muted" dir="ltr">{me.data.user.email}</span>}
              <button type="button" onClick={() => signOut.mutate()} disabled={signOut.isPending} className={btn}>{t("auth.signOut")}</button>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => signOutEverywhere.mutate()} disabled={signOutEverywhere.isPending} className={btn}>{t("auth.signOutEverywhere")}</button>
              <span className="text-muted">{t("auth.signOutEverywhereHelp")}</span>
            </div>
          </div>
        )}
        {me.data?.sso_configured && !me.data.user && (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-muted">{t("auth.ssoHelp")}</span>
            <a href={signInUrl("/settings")} className={btnPrimary}>{t("auth.signIn")}</a>
          </div>
        )}
      </Card>
      {me.data?.user && profile.data && (
        <Card title={t("persona.title")}>
          <p className="mb-3 text-sm text-muted">{t("persona.chooseHelp")}</p>
          <PersonaPicker profile={profile.data} />
        </Card>
      )}
      {me.data?.user && (
        <Card title={t("profile.yourData")}>
          <p className="text-sm text-muted">{t("profile.yourDataHelp")}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {forget.isSuccess && !confirmForget ? (
              <span role="status" className="text-sm text-ok">{t("profile.forgotten")}</span>
            ) : !confirmForget ? (
              <button type="button" onClick={() => setConfirmForget(true)} className={btn}>{t("profile.forget")}</button>
            ) : (
              <>
                <button type="button" onClick={() => { forget.mutate(undefined, { onSuccess: () => clearNudgeState(me.data?.user?.sub), onSettled: () => setConfirmForget(false) }); }} disabled={forget.isPending} className={btnDanger}>{t("profile.forgetConfirm")}</button>
                <button type="button" onClick={() => setConfirmForget(false)} className={btn}>{t("common.cancel")}</button>
              </>
            )}
          </div>
        </Card>
      )}
      <Card title={t("settings.apiKey")}>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); save(key); }}>
          <p className="text-sm text-muted">{t("settings.apiKeyHelp")}</p>
          <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} aria-label={t("settings.apiKey")}
            className={`${input} font-mono`} dir="ltr" />
          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className={btnPrimary}>{t("settings.save")}</button>
            <button type="button" onClick={() => save("")} className={btn}>{t("settings.clear")}</button>
            {saved && key === stored && <span role="status" className="motion-safe:animate-scale-in text-sm text-ok">{t("settings.saved")}</span>}
            {key !== stored && <span className="text-sm text-muted">{t("settings.unsaved")}</span>}
          </div>
        </form>
        {me.error && <div className="mt-3"><ErrorBox error={me.error} onRetry={() => me.refetch()} /></div>}
        {me.data && (
          <dl className="mt-4 grid grid-cols-[160px_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-t border-rule pt-3 text-[13px]">
            <dt className="text-[12px] font-medium text-muted">{t("settings.role")}</dt>
            <dd data-testid="settings-role">
              {t(`roles.${me.data.role}`)}
              {me.data.operator_via && <span className="text-muted"> · {t(me.data.operator_via === "key" ? "auth.operatorViaKey" : "auth.operatorViaGroup")}</span>}
            </dd>
            <dt className="text-[12px] font-medium text-muted">{t("settings.liveAllowed")}</dt><dd>{yesNo(me.data.live_allowed)}</dd>
            <dt className="text-[12px] font-medium text-muted">{t("settings.atlassian")}</dt><dd>{yesNo(me.data.atlassian_configured)}</dd>
          </dl>
        )}
      </Card>
      <Card title={t("settings.language")}><LanguageSwitcher /></Card>
      <Card title={t("settings.contract")}>
        {contract.isPending ? <Loading /> : contract.error ? <ErrorBox error={contract.error} onRetry={() => contract.refetch()} /> : (
          <pre dir="ltr" className="overflow-x-auto rounded-s border border-rule bg-surface-2 p-3 font-mono text-[11.5px] leading-[1.5] text-ink-2">{JSON.stringify(contract.data, null, 1)}</pre>
        )}
      </Card>
      {me.data?.user && (
        <Card title={t("nudges.settingsTitle")}>
          <p className="text-sm text-muted">{t("nudges.settingsHelp")}</p>
          <div className="mt-3"><SuggestionsToggle sub={me.data.user.sub} /></div>
        </Card>
      )}
    </div>
  );
}
