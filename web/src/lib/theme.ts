import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

/** Shared with the inline boot script in index.html — keep the two in sync. */
export const THEME_KEY = "ffdraft-theme";

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null; // private mode / storage disabled
  }
}

function prefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function readTheme(): Theme {
  return stored() ?? (prefersDark() ? "dark" : "light");
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

/**
 * Theme state for the whole app. The class is already on <html> before React mounts
 * (see the boot script in index.html), so this only keeps it in step afterwards.
 *
 * Nothing is written to storage until the user actually picks a side — otherwise the
 * first render would silently record the OS preference as a choice and the app would
 * stop following the OS from then on.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // ignore: the class still flips, the choice just won't survive a reload
    }
  }, []);

  // Follow the OS for as long as the user has not chosen for themselves.
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => {
      if (stored() === null) setThemeState(e.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);
  return { theme, dark: theme === "dark", setTheme, toggle };
}
