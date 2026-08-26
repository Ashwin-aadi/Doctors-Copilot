import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import type { Role } from "../store/auth";
import { Forbidden } from "../app/Forbidden";
import { ROUTES } from "./routes";

export interface ProtectedRouteProps {
  roles: Role[];
  children: ReactNode;
}

export function ProtectedRoute({ roles, children }: ProtectedRouteProps) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return null;

  if (!isAuthenticated || !user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${ROUTES.login}?next=${next}`} replace />;
  }

  if (!roles.includes(user.role)) {
    return <Forbidden />;
  }

  if (user.role === "patient" && !user.patientId && location.pathname !== ROUTES.onboarding) {
    return <Navigate to={ROUTES.onboarding} replace />;
  }

  return <>{children}</>;
}
