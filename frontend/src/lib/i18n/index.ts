import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../../locales/en/common.json";
import hi from "../../locales/hi/common.json";

export const SUPPORTED_LANGUAGES = ["en", "hi"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const LANG_COOKIE = "docopilot_lang";

export function readLanguageCookie(): SupportedLanguage {
  const match = document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=([^;]*)`));
  const value = match ? decodeURIComponent(match[1]) : null;
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(value ?? "")
    ? (value as SupportedLanguage)
    : (navigator.language.toLowerCase().startsWith("hi") ? "hi" : "en");
}

export function writeLanguageCookie(lang: SupportedLanguage): void {
  document.cookie = `${LANG_COOKIE}=${lang}; path=/; max-age=31536000; samesite=lax`;
}

export async function initI18n(): Promise<SupportedLanguage> {
  const lang = readLanguageCookie();
  await i18n.use(initReactI18next).init({
    resources: { en: { common: en }, hi: { common: hi } },
    lng: lang,
    fallbackLng: "en",
    defaultNS: "common",
    interpolation: { escapeValue: false },
  });
  return lang;
}

export function changeLanguage(lang: SupportedLanguage): void {
  writeLanguageCookie(lang);
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
}

export default i18n;
