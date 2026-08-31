import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { cn } from "../lib/cn";
import { ErrorBoundary } from "./ErrorBoundary";
import { AUTH_ROUTES } from "../router/routes";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Two layouts, one route tree.
 *
 * Signed in, the app is a workstation: a fixed rail, a sticky bar and a
 * scrolling work area. Signed out, there is nothing to navigate, so the auth
 * screens get the whole viewport and render their own centred panel rather
 * than a shell wrapped around an empty rail.
 *
 * The auth screens keep that bare treatment even when a session exists: they
 * are their own full-viewport panel, and a rail around one belongs to an
 * account the user is in the middle of leaving.
 */
export function RootLayout() {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  useTheme();

  // A route change while the mobile drawer is open would otherwise leave it
  // covering the page the user just asked for.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  if (!isAuthenticated || !user || AUTH_ROUTES.includes(location.pathname)) {
    return (
      <div className="min-h-screen bg-bg text-fg">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-bg text-fg">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 hidden shrink-0 border-r border-rail-border transition-[width] duration-200 ease-smooth lg:block",
          collapsed ? "w-rail-sm" : "w-rail",
        )}
      >
        <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
      </aside>

      {/* Mobile: the same rail, as a dismissible drawer. */}
      {drawerOpen && (
        <>
          <div
            className="fixed inset-0 z-40 animate-fade-in bg-black/50 backdrop-blur-sm lg:hidden"
            aria-hidden="true"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="fixed inset-y-0 left-0 z-50 w-rail animate-slide-in-left shadow-lg lg:hidden">
            <Sidebar
              collapsed={false}
              onToggleCollapsed={() => setDrawerOpen(false)}
              onNavigate={() => setDrawerOpen(false)}
            />
          </aside>
        </>
      )}

      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col transition-[padding] duration-200 ease-smooth",
          collapsed ? "lg:pl-rail-sm" : "lg:pl-rail",
        )}
      >
        <Topbar onOpenSidebar={() => setDrawerOpen(true)} />
        {/* Keyed on the path so every route replays its entrance rather than
            swapping content inside a static frame. */}
        <main key={location.pathname} className="min-w-0 flex-1">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
