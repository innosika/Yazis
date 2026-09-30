/**
 * Light / dark / system theme.
 *
 * `theme.css` reacts to two signals: the OS `prefers-color-scheme` media query, and an
 * explicit `data-theme` attribute on <html> that wins in either direction. "system" is
 * simply the absence of the attribute. The choice persists in localStorage and a tiny
 * inline script in index.html applies it before the first paint.
 */
import { useCallback, useSyncExternalStore } from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "irs.theme";
const listeners = new Set<() => void>();

function readPreference(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(preference: ThemePreference): void {
  const root = document.documentElement;
  if (preference === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", preference);
  try {
    if (preference === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Storage may be unavailable (private mode); the attribute alone still works.
  }
  for (const listener of listeners) listener();
}

export function resolveTheme(preference: ThemePreference = readPreference()): ResolvedTheme {
  if (preference !== "system") return preference;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", listener);
    window.removeEventListener("storage", listener);
  };
}

export function useTheme(): {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (next: ThemePreference) => void;
} {
  const preference = useSyncExternalStore(subscribe, readPreference, () => "system" as const);
  const resolved = useSyncExternalStore(
    subscribe,
    () => resolveTheme(readPreference()),
    () => "light" as const,
  );
  const setPreference = useCallback((next: ThemePreference) => applyTheme(next), []);
  return { preference, resolved, setPreference };
}
