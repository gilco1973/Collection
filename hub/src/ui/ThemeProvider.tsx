import { useEffect, type ReactNode } from "react";
import { useAuth } from "../auth/AuthProvider";

/**
 * Applies the person's theme and density preferences to the document root.
 * `system` removes the stamp so `prefers-color-scheme` decides; an explicit
 * choice stamps `data-theme` and wins over the OS setting.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { principal } = useAuth();
  const theme = principal?.preferences.theme ?? "system";
  const density = principal?.preferences.density ?? "comfortable";
  const a11y = principal?.preferences.accessibility ?? false;
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    root.dataset.density = density;
    if (a11y) root.dataset.a11y = "true";
    else delete root.dataset.a11y;
    // "system": mirror the OS preference as a class so the dark tokens apply
    // without a stamp, and follow it live.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => root.classList.toggle("dark-system", theme === "system" && mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme, density, a11y]);
  return <>{children}</>;
}
