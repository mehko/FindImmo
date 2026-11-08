import type { ThemeSetting } from "./types";

/** Applique le thème ; une copie est gardée dans localStorage pour l'appliquer avant le rendu. */
export function applyTheme(theme: ThemeSetting): void {
  try {
    localStorage.setItem("findimmo-theme", theme);
  } catch {
    /* stockage indisponible : thème appliqué pour la session seulement */
  }
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
