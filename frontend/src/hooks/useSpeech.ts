import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Text-to-speech for the interviewer, using the browser's Web Speech API.
 *
 * Voices load asynchronously in most browsers, so this listens for
 * `voiceschanged` rather than reading `getVoices()` once.
 */
export function useSpeech() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [speaking, setSpeaking] = useState(false);
  const supported =
    typeof window !== "undefined" && "speechSynthesis" in window;
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (!supported) return;
    const load = () => {
      const all = window.speechSynthesis.getVoices();
      // Prefer English voices for an English-language interview.
      setVoices(all.filter((v) => v.lang.toLowerCase().startsWith("en")));
    };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", load);
      window.speechSynthesis.cancel();
    };
  }, [supported]);

  const cancel = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string, voiceURI?: string, rate = 0.95) => {
      if (!supported || !text.trim()) return;
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      const voice = voiceURI
        ? window.speechSynthesis.getVoices().find((v) => v.voiceURI === voiceURI)
        : undefined;
      if (voice) utterance.voice = voice;
      utterance.rate = rate;
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [supported]
  );

  return { supported, voices, speaking, speak, cancel };
}
