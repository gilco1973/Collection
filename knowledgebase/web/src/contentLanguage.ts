import { useSyncExternalStore } from "react";

/** The language a reader views *page content* in — independent of the console's own UI language (i18n/index.ts). */
export interface ContentLanguage {
  code: string;
  label: string;
  flag: string;
  rtl?: boolean;
}

export const CONTENT_LANGUAGES: ContentLanguage[] = [
  { code: "en", label: "English", flag: "🇺🇸" },
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "he", label: "עברית", flag: "🇮🇱", rtl: true },
];

const STORAGE_KEY = "kb.contentLanguage";
const listeners = new Set<() => void>();

function readStored(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && CONTENT_LANGUAGES.some((l) => l.code === stored) ? stored : "en";
  } catch {
    return "en";
  }
}

let current = readStored();

export function setContentLanguage(code: string): void {
  if (code === current) return;
  current = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* per-viewer convenience only; the selection still applies for this session */
  }
  listeners.forEach((notify) => notify());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** The current content language code; re-renders the caller on every `setContentLanguage`. */
export function useContentLanguage(): string {
  return useSyncExternalStore(subscribe, () => current);
}

export function isRtlContentLanguage(code: string): boolean {
  return CONTENT_LANGUAGES.find((l) => l.code === code)?.rtl ?? false;
}
