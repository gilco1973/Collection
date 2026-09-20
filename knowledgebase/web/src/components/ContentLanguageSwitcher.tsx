import { useTranslation } from "react-i18next";
import { CONTENT_LANGUAGES, setContentLanguage, useContentLanguage } from "../contentLanguage";

/** `available` narrows the list to what the backend actually serves (English is always the source). */
export default function ContentLanguageSwitcher({ available }: { available?: string[] }) {
  const { t } = useTranslation();
  const current = useContentLanguage();
  const options = available ? CONTENT_LANGUAGES.filter((l) => l.code === "en" || available.includes(l.code)) : CONTENT_LANGUAGES;
  return (
    <label className="text-xs">
      <span className="sr-only">{t("page.contentLanguage")}</span>
      <select
        aria-label={t("page.contentLanguage")}
        data-testid="content-language-select"
        className="rounded border border-rule bg-surface px-2 py-1 text-xs"
        value={current}
        onChange={(e) => setContentLanguage(e.target.value)}
      >
        {options.map((l) => (
          <option key={l.code} value={l.code}>
            {l.flag} {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
