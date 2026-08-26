import type { Theme } from "../store/ui";

const THEME_COOKIE = "docopilot_theme";

export function readThemeCookie(): Theme {
  const match = document.cookie.match(new RegExp(`(?:^|; )${THEME_COOKIE}=([^;]*)`));
  const value = match ? decodeURIComponent(match[1]) : null;
  return value === "dark" ? "dark" : "light";
}

export function writeThemeCookie(theme: Theme): void {
  document.cookie = `${THEME_COOKIE}=${theme}; path=/; max-age=31536000; samesite=lax`;
}
