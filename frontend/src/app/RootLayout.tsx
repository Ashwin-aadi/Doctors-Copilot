import { Outlet, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Stethoscope, Globe } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { changeLanguage, type SupportedLanguage } from "../lib/i18n";
import { Button } from "../components/ui/Button";
import { ErrorBoundary } from "./ErrorBoundary";

export function RootLayout() {
  const { t, i18n } = useTranslation();
  const { user, isAuthenticated, logout } = useAuth();
  useTheme();

  function toggleLanguage() {
    const next: SupportedLanguage = i18n.language === "hi" ? "en" : "hi";
    changeLanguage(next);
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg text-fg">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <Stethoscope className="h-5 w-5 text-primary" aria-hidden="true" />
          {t("app.name")}
        </Link>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-fg-muted sm:inline">{t("nav.emergency")}</span>
          <Button variant="ghost" size="sm" leftIcon={<Globe className="h-4 w-4" />} onClick={toggleLanguage}>
            {i18n.language === "hi" ? "EN" : "हि"}
          </Button>
          {isAuthenticated && user && (
            <Button variant="ghost" size="sm" onClick={logout}>
              {t("nav.logout")}
            </Button>
          )}
        </div>
      </header>
      <main className="flex-1">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}
