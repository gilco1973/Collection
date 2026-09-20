import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import bn from "./locales/bn.json";
import en from "./locales/en.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import he from "./locales/he.json";
import hi from "./locales/hi.json";
import it from "./locales/it.json";
import ja from "./locales/ja.json";
import ta from "./locales/ta.json";
import zh from "./locales/zh.json";

export const LANGUAGES: { code: string; label: string; rtl?: boolean }[] = [
  { code: "en", label: "English" },
  { code: "he", label: "עברית", rtl: true },
  { code: "es", label: "Español" },
  { code: "zh", label: "中文" },
  { code: "fr", label: "Français" },
  { code: "it", label: "Italiano" },
  { code: "hi", label: "हिन्दी" },
  { code: "ta", label: "தமிழ்" },
  { code: "bn", label: "বাংলা" },
  { code: "ja", label: "日本語" },
];

const STORAGE_KEY = "kb.language";

export function readStoredLanguage(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "en";
  } catch {
    return "en";
  }
}

export function applyDirection(code: string): void {
  const rtl = LANGUAGES.find((l) => l.code === code)?.rtl ?? false;
  document.documentElement.setAttribute("dir", rtl ? "rtl" : "ltr");
  document.documentElement.setAttribute("lang", code);
}

export function changeLanguage(code: string): Promise<unknown> {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* storage unavailable: language still changes for this session */
  }
  applyDirection(code);
  return i18next.changeLanguage(code);
}

export function initI18n(language = readStoredLanguage()) {
  if (!i18next.isInitialized) {
    i18next.use(initReactI18next).init({
      resources: { en: { translation: en }, he: { translation: he }, es: { translation: es }, zh: { translation: zh }, fr: { translation: fr }, it: { translation: it }, hi: { translation: hi }, ta: { translation: ta }, bn: { translation: bn }, ja: { translation: ja } },
      lng: language,
      fallbackLng: "en",
      interpolation: { escapeValue: false },
    });
  }
  applyDirection(language);
  return i18next;
}
