import { useUiStore } from "../store/ui";
import { writeThemeCookie } from "../lib/theme";

export function useTheme() {
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);

  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    writeThemeCookie(next);
    setTheme(next);
  }

  return { theme, toggle };
}
