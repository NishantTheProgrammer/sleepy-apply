"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

type Theme =
  | "default"
  | "emerald"
  | "rose"
  | "ocean"
  | "cyberpunk"
  | "forest"
  | "amethyst"
  | "monochrome";

const THEMES: Theme[] = [
  "default", "emerald", "rose", "ocean", "cyberpunk", "forest", "amethyst", "monochrome",
];

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  themes: Theme[];
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("default");

  useEffect(() => {
    const saved = localStorage.getItem("sa-theme") as Theme | null;
    if (saved && THEMES.includes(saved)) setThemeState(saved);
  }, []);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem("sa-theme", t);
    document.documentElement.setAttribute("data-theme", t === "default" ? "" : t);
  };

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme === "default" ? "" : theme);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
