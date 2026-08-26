import { useAuthStore } from "../store/auth";

export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);
  const clear = useAuthStore((s) => s.clear);
  return {
    user,
    status,
    isAuthenticated: status === "authenticated",
    isLoading: status === "idle",
    logout: clear,
  };
}
