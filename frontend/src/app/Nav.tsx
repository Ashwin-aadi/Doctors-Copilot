import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "../lib/cn";
import { useAuth } from "../hooks/useAuth";
import { ROUTES } from "../router/routes";
import type { Role } from "../store/auth";

interface NavItem {
  to: string;
  labelKey: string;
}

const LINKS_BY_ROLE: Record<Role, NavItem[]> = {
  patient: [
    { to: ROUTES.chat, labelKey: "nav.chat" },
    { to: ROUTES.booking, labelKey: "nav.booking" },
    { to: ROUTES.portal, labelKey: "nav.portal" },
    { to: ROUTES.abha, labelKey: "nav.abha" },
  ],
  doctor: [
    { to: ROUTES.doctorHome, labelKey: "nav.doctorHome" },
    { to: ROUTES.doctorQueue, labelKey: "nav.doctorQueue" },
  ],
  staff: [
    { to: ROUTES.doctorHome, labelKey: "nav.doctorHome" },
    { to: ROUTES.doctorQueue, labelKey: "nav.doctorQueue" },
  ],
  admin: [{ to: ROUTES.adminRoot, labelKey: "nav.admin" }],
};

/**
 * Which links render is derived solely from `auth.user.role` -- never from
 * the current route -- so the nav stays correct even on routes shared
 * across roles (e.g. `/visit/:id`).
 */
export function Nav() {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (!user) return null;

  const links = LINKS_BY_ROLE[user.role] ?? [];
  if (links.length === 0) return null;

  return (
    <nav className="hidden items-center gap-4 text-sm sm:flex">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) =>
            cn("text-fg-muted hover:text-fg", isActive && "font-semibold text-fg")
          }
        >
          {t(link.labelKey)}
        </NavLink>
      ))}
    </nav>
  );
}
