import { useEffect } from "react";
import { useTranslation } from "react-i18next";

/** Sets `document.title` to "<page> · <app>" for the lifetime of the page. */
export function usePageTitle(title: string | undefined): void {
  const { t } = useTranslation();
  useEffect(() => {
    const app = t("app.title");
    document.title = title ? `${title} · ${app}` : app;
  }, [title, t]);
}
