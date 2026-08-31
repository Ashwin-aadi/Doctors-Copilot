import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Globe, LogOut, Menu, Moon, PhoneCall, Sun } from "lucide-react";
import { Avatar } from "../components/ui/Avatar";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { changeLanguage, type SupportedLanguage } from "../lib/i18n";
import { NotificationsContainer } from "../features/notifications/NotificationsContainer";
import { cn } from "../lib/cn";
import { pageTitleKey } from "./pageMeta";

export interface TopbarProps {
  onOpenSidebar: () => void;
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-9 w-9 items-center justify-center rounded-md text-fg-muted transition-[background-color,color,transform] duration-150 ease-out hover:bg-surface-2 hover:text-fg active:scale-95"
    >
      {children}
    </button>
  );
}

/**
 * The bar answers three questions at a glance: where am I, who am I signed in
 * as, and where do I call if this turns into an emergency. Everything else it
 * offers is a preference toggle and is pushed to the right.
 */
export function Topbar({ onOpenSidebar }: TopbarProps) {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const { theme, toggle: toggleTheme } = useTheme();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // The bar is translucent, so without a hairline shadow the content scrolling
  // under it has no edge to disappear behind.
  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 4);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function toggleLanguage() {
    const next: SupportedLanguage = i18n.language === "hi" ? "en" : "hi";
    void changeLanguage(next);
  }

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b bg-surface/80 px-4 backdrop-blur-md sm:px-6",
        "transition-[box-shadow,border-color] duration-200",
        scrolled ? "border-border shadow-sm" : "border-transparent",
      )}
    >
      <button
        type="button"
        aria-label={t("nav.openMenu")}
        onClick={onOpenSidebar}
        className="flex h-9 w-9 items-center justify-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-fg lg:hidden"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      <h1
        key={location.pathname}
        className="min-w-0 flex-1 animate-fade-in truncate text-base font-semibold text-fg"
      >
        {t(pageTitleKey(location.pathname))}
      </h1>

      <span className="hidden items-center gap-1.5 rounded-full border border-critical/30 bg-critical-soft px-3 py-1 text-xs font-semibold text-critical-soft-fg shadow-xs md:inline-flex">
        <span className="relative flex h-2 w-2" aria-hidden="true">
          <span className="absolute inset-0 rounded-full bg-critical/50 animate-pulse-ring" />
          <span className="relative h-2 w-2 rounded-full bg-critical" />
        </span>
        <PhoneCall className="h-3.5 w-3.5" aria-hidden="true" />
        {t("nav.emergency")}
      </span>

      <div className="flex items-center gap-0.5">
        <IconButton label={t("nav.toggleLanguage")} onClick={toggleLanguage}>
          <span className="relative">
            <Globe className="h-[18px] w-[18px]" aria-hidden="true" />
            <span className="absolute -bottom-1.5 -right-1.5 text-[9px] font-bold">
              {i18n.language === "hi" ? "EN" : "हि"}
            </span>
          </span>
        </IconButton>
        <IconButton label={t("nav.toggleTheme")} onClick={toggleTheme}>
          {theme === "dark" ? (
            <Sun className="h-[18px] w-[18px]" aria-hidden="true" />
          ) : (
            <Moon className="h-[18px] w-[18px]" aria-hidden="true" />
          )}
        </IconButton>
        {user && <NotificationsContainer />}
      </div>

      {user && (
        <div className="relative ml-1">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 transition-colors duration-150 hover:bg-surface-2"
          >
            <Avatar name={user.name ?? user.email} size="sm" />
            <span className="hidden max-w-[10rem] truncate text-sm font-medium text-fg sm:inline">
              {user.name ?? user.email}
            </span>
          </button>

          {menuOpen && (
            <>
              <div
                className="fixed inset-0 z-10"
                aria-hidden="true"
                onClick={() => setMenuOpen(false)}
              />
              <div
                role="menu"
                className={cn(
                  "absolute right-0 z-20 mt-2 w-56 origin-top-right overflow-hidden rounded-lg border border-border bg-surface shadow-lg",
                  "animate-scale-in",
                )}
              >
                <div className="border-b border-border px-4 py-3">
                  <p className="truncate text-sm font-medium text-fg">{user.name ?? user.email}</p>
                  <p className="truncate text-xs text-fg-muted">{user.email}</p>
                </div>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                  }}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-fg transition-colors duration-150 hover:bg-critical-soft hover:text-critical-soft-fg"
                >
                  <LogOut className="h-4 w-4 text-fg-muted" aria-hidden="true" />
                  {t("nav.logout")}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </header>
  );
}
