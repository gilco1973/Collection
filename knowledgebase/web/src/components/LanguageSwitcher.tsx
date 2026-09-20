import { useTranslation } from "react-i18next";
import { changeLanguage, LANGUAGES } from "../i18n";

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  return (
    <label className="text-xs">
      <span className="sr-only">{t("settings.language")}</span>
      <select
        aria-label={t("settings.language")}
        data-testid="ui-language-select"
        className="rounded border border-rule bg-surface px-2 py-1 text-xs"
        value={i18n.language}
        onChange={(e) => void changeLanguage(e.target.value)}
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
