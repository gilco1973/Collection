import { useTranslation } from "react-i18next";
import { useVoiceInput } from "../useVoiceInput";

/** Mic button that dictates one utterance into `onResult`; renders nothing where SpeechRecognition is unsupported (e.g. Firefox). */
export default function VoiceInputButton({ onResult }: { onResult: (text: string) => void }) {
  const { t, i18n } = useTranslation();
  const { supported, listening, start, stop } = useVoiceInput(i18n.language, onResult);
  if (!supported) return null;
  return (
    <button type="button" onClick={() => (listening ? stop() : start())} aria-pressed={listening}
      aria-label={t(listening ? "search.voiceListening" : "search.voiceInput")}
      className={`flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-s transition-colors hover:bg-surface-2 ${listening ? "motion-safe:animate-pulse text-accent" : "text-muted hover:text-ink"}`}>
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-[16px] w-[16px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="9" y="2" width="6" height="12" rx="3" />
        <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
        <path d="M12 18v3" />
      </svg>
    </button>
  );
}
