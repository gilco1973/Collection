import { useCallback, useEffect, useRef, useState } from "react";

// BCP-47 tags for the console's 10 supported languages; SpeechRecognition needs a region.
const RECOGNITION_LANG: Record<string, string> = {
  en: "en-US", he: "he-IL", es: "es-ES", zh: "zh-CN", fr: "fr-FR",
  it: "it-IT", hi: "hi-IN", ta: "ta-IN", bn: "bn-IN", ja: "ja-JP",
};

function recognitionCtor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

/** Dictates one utterance at a time via the browser's SpeechRecognition; `onResult` fires once per utterance. */
export function useVoiceInput(lang: string, onResult: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;
  // Checked per render, not cached at module load: support can only be known once `window` exists,
  // and tests stub it in after this module is first imported.
  const supported = recognitionCtor() !== null;

  useEffect(() => () => recognitionRef.current?.stop(), []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const recognition = new Ctor();
    recognition.lang = RECOGNITION_LANG[lang] ?? "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (e) => {
      const text = e.results[0]?.[0]?.transcript;
      if (text) onResultRef.current(text);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }, [lang]);

  const stop = useCallback(() => recognitionRef.current?.stop(), []);

  return { supported, listening, start, stop };
}
