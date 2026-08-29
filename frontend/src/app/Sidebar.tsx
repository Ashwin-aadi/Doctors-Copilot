import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, PanelLeftOpen, PhoneCall, Stethoscope } from "lucide-react";
import { cn } from "../lib/cn";
import { useAuth } from "../hooks/useAuth";
import { Nav } from "./Nav";

export interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** Called after any navigation, so the mobile drawer closes behind the user. */
  onNavigate?: () => void;
}

const ROLE_LABEL_KEY: Record<string, string> = {
  patient: "roles.patient",
  doctor: "roles.doctor",
  staff: "roles.staff",
  admin: "roles.admin",
};

/**
 * The navigation rail.
 *
 * Dark, narrow and constant: it is the one part of the screen that never
 * changes between the triage chat, the queue board and the visit workspace, so
 * it carries the product identity and the emergency numbers and otherwise
 * stays out of the way of the clinical colour on the page.
 */
export function Sidebar({ collapsed, onToggleCollapsed, onNavigate }: SidebarProps) {
  const { t } = useTranslation();
  const { user } = useAuth();

  return (
    <div className="flex h-full flex-col bg-rail text-rail-fg">
      <div
        className={cn(
          "flex h-16 items-center gap-2.5 border-b border-rail-border px-4",
          collapsed && "justify-center px-0",
        )}
      >
        <Link
          to="/"
          onClick={onNavigate}
          className="flex min-w-0 items-center gap-2.5 font-semibold text-rail-fg"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary text-primary-fg">
            <Stethoscope className="h-5 w-5" aria-hidden="true" />
          </span>
          {!collapsed && (
            <span className="flex min-w-0 flex-col leading-tight">
              <span className="truncate text-sm">{t("app.name")}</span>
              <span className="truncate text-[11px] font-normal text-rail-muted">
                {t("app.tagline")}
              </span>
            </span>
          )}
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        {!collapsed && (
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-rail-muted">
            {t("nav.sectionWorkspace")}
          </p>
        )}
        <Nav collapsed={collapsed} onNavigate={onNavigate} />
      </div>

      <div className="border-t border-rail-border p-3">
        {/* Emergency routing is the one thing that must be reachable from every
            screen without reading anything else, so it lives in the rail. */}
        <div
          className={cn(
            "rounded-md bg-rail-2 p-3",
            collapsed && "flex justify-center p-2",
          )}
        >
          {collapsed ? (
            <PhoneCall className="h-5 w-5 text-critical" aria-hidden="true" />
          ) : (
            <>
              <p className="flex items-center gap-2 text-xs font-semibold text-rail-fg">
                <PhoneCall className="h-4 w-4 text-critical" aria-hidden="true" />
                {t("emergencyCard.title")}
              </p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-rail-muted">
                {t("emergencyCard.body")}
              </p>
            </>
          )}
        </div>

        {user && !collapsed && (
          <p className="mt-3 truncate px-1 text-[11px] text-rail-muted">
            {t(ROLE_LABEL_KEY[user.role] ?? "roles.patient")} · {user.email}
          </p>
        )}

        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
          className={cn(
            "mt-3 hidden w-full items-center gap-2 rounded-md px-3 py-2 text-xs font-medium text-rail-muted transition-colors hover:bg-rail-active hover:text-rail-fg lg:flex",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
              {t("nav.collapse")}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
