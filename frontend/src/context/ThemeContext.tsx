"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Theme =
  | "default"
  | "emerald"
  | "rose"
  | "ocean"
  | "cyberpunk"
  | "forest"
  | "amethyst"
  | "monochrome";

export interface ThemeConfig {
  id: Theme;
  name: string;
  colors: [string, string];
  description: string;
}

export const THEME_CONFIGS: Record<Theme, ThemeConfig> = {
  default: {
    id: "default",
    name: "Twilight",
    colors: ["#4f46e5", "#9333ea"],
    description: "Default indigo & purple",
  },
  emerald: {
    id: "emerald",
    name: "Aurora",
    colors: ["#10b981", "#06b6d4"],
    description: "Vibrant emerald & cyan",
  },
  rose: {
    id: "rose",
    name: "Sunset",
    colors: ["#e11d48", "#f59e0b"],
    description: "Warm rose & amber",
  },
  ocean: {
    id: "ocean",
    name: "Deep Ocean",
    colors: ["#3b82f6", "#06b6d4"],
    description: "Cool blue & cyan",
  },
  cyberpunk: {
    id: "cyberpunk",
    name: "Cyberpunk",
    colors: ["#db2777", "#eab308"],
    description: "High-contrast neon pink & yellow",
  },
  forest: {
    id: "forest",
    name: "Forest",
    colors: ["#15803d", "#84cc16"],
    description: "Earthy green & lime",
  },
  amethyst: {
    id: "amethyst",
    name: "Amethyst",
    colors: ["#7e22ce", "#4338ca"],
    description: "Deep purple & rich indigo",
  },
  monochrome: {
    id: "monochrome",
    name: "Stealth",
    colors: ["#64748b", "#334155"],
    description: "Monochrome slate",
  },
};

export const THEMES: Theme[] = [
  "default",
  "emerald",
  "rose",
  "ocean",
  "cyberpunk",
  "forest",
  "amethyst",
  "monochrome",
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
