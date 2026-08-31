import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { homeForRole } from "./routes";

/**
 * The mirror of `ProtectedRoute`: keeps a signed-in user off the sign-in and
 * sign-up screens. Without it a logged-in doctor opening /register was shown
 * an account-creation form -- framed, confusingly, by their own workspace.
 */
export function GuestRoute({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;
  if (isAuthenticated && user) return <Navigate to={homeForRole(user.role)} replace />;

  return <>{children}</>;
}
