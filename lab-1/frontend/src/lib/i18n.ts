/**
 * Minimal localisation: Russian by default, English on demand.
 *
 * Strings are keyed by their English source text, so components stay readable
 * (`t("Search the collection")`) and English needs no dictionary. `{name}` placeholders are
 * substituted from `params`. The page tree is remounted on a language change (see
 * RootLayout), so plain module-level helpers may call `t()` at render time.
 */
import { useCallback, useSyncExternalStore } from "react";
import { ru } from "./locales/ru";

export type Lang = "ru" | "en";

const STORAGE_KEY = "irs.lang";
const listeners = new Set<() => void>();
let current: Lang = readLang();

function readLang(): Lang {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "en" ? "en" : "ru";
  } catch {
    return "ru";
  }
}

export function getLang(): Lang {
  return current;
}

export function setLang(next: Lang): void {
  current = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // storage unavailable — the in-memory value still applies
  }
  document.documentElement.lang = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export type Params = Record<string, string | number>;

export function t(source: string, params?: Params): string {
  const text = current === "ru" ? (ru[source] ?? source) : source;
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (match, name: string) => (name in params ? String(params[name]) : match));
}

/** Pick one of two already-localised strings. */
export const pick = (ruText: string, enText: string): string => (current === "ru" ? ruText : enText);

export function useLang(): { lang: Lang; setLang: (next: Lang) => void; t: typeof t } {
  const lang = useSyncExternalStore(subscribe, getLang, () => "ru" as const);
  const set = useCallback((next: Lang) => setLang(next), []);
  return { lang, setLang: set, t };
}

/** Locale for number/date formatting. */
export const locale = (): string => (current === "ru" ? "ru-RU" : "en-GB");
