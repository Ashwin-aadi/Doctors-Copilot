import type { ComponentType } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CalendarPlus,
  ClipboardList,
  LayoutDashboard,
  MessageSquareHeart,
  Stethoscope,
  Users,
} from "lucide-react";
import { cn } from "../lib/cn";
import { useAuth } from "../hooks/useAuth";
import { ROUTES } from "../router/routes";
import type { Role } from "../store/auth";

interface NavItem {
  to: string;
  labelKey: string;
  icon: ComponentType<{ className?: string }>;
  /** `end` for routes that prefix-match a deeper one (e.g. /doctor). */
  end?: boolean;
}

const LINKS_BY_ROLE: Record<Role, NavItem[]> = {
  patient: [
    { to: ROUTES.chat, labelKey: "nav.chat", icon: Stethoscope },
    { to: ROUTES.assistant, labelKey: "nav.assistant", icon: MessageSquareHeart },
    { to: ROUTES.booking, labelKey: "nav.booking", icon: CalendarPlus },
    { to: ROUTES.portal, labelKey: "nav.portal", icon: ClipboardList },
  ],
  doctor: [
    { to: ROUTES.doctorHome, labelKey: "nav.doctorHome", icon: LayoutDashboard, end: true },
    { to: ROUTES.doctorQueue, labelKey: "nav.doctorQueue", icon: Users },
  ],
  staff: [
    { to: ROUTES.doctorHome, labelKey: "nav.doctorHome", icon: LayoutDashboard, end: true },
    { to: ROUTES.doctorQueue, labelKey: "nav.doctorQueue", icon: Users },
  ],
  admin: [
    { to: ROUTES.doctorHome, labelKey: "nav.doctorHome", icon: LayoutDashboard, end: true },
    { to: ROUTES.doctorQueue, labelKey: "nav.doctorQueue", icon: Users },
  ],
};

export interface NavProps {
  /** Collapsed rail: icons only, label carried by the title attribute. */
  collapsed?: boolean;
  onNavigate?: () => void;
}

/**
 * Which links render is derived solely from `auth.user.role` -- never from the
 * current route -- so the nav stays correct even on routes shared across roles
 * (e.g. `/visit/:id`).
 */
export function Nav({ collapsed = false, onNavigate }: NavProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (!user) return null;

  const links = LINKS_BY_ROLE[user.role] ?? [];
  if (links.length === 0) return null;

  return (
    <nav aria-label={t("nav.primary")} className="flex flex-col gap-1">
      {links.map((link) => {
        const Icon = link.icon;
        const label = t(link.labelKey);
        return (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                collapsed && "justify-center px-0",
                isActive
                  ? "bg-rail-active text-rail-fg"
                  : "text-rail-muted hover:bg-rail-active/60 hover:text-rail-fg",
              )
            }
          >
            {({ isActive }) => (
              <>
                {/* The active marker is a rail against the edge rather than a
                    filled pill, so the eye finds the current section without
                    the nav competing with the clinical colour on the page. */}
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute left-0 h-5 w-0.5 rounded-r bg-primary transition-opacity",
                    isActive ? "opacity-100" : "opacity-0",
                  )}
                />
                <Icon className="h-[18px] w-[18px] shrink-0" />
                {!collapsed && <span className="truncate">{label}</span>}
              </>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}
