import { useEffect, type ReactNode } from "react";
import { env } from "../lib/env";
import { me } from "../lib/api/endpoints/auth";
import { useAuthStore, type AuthUser } from "../store/auth";

function toAuthUser(profile: Awaited<ReturnType<typeof me>>): AuthUser {
  return {
    id: profile.id,
    email: profile.email,
    role: profile.role,
    name: profile.name,
    patientId: profile.patient?.id,
    doctorId: profile.doctor?.id,
    nmcRegNo: profile.doctor?.nmc_reg_no ?? undefined,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const setSession = useAuthStore((s) => s.setSession);
  const clear = useAuthStore((s) => s.clear);

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      try {
        const res = await fetch(`${env.apiBase}/api/v1/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        if (!res.ok) throw new Error("no session");
        const body = (await res.json()) as { access_token: string };
        if (cancelled) return;
        useAuthStore.setState({ accessToken: body.access_token });
        const profile = await me();
        if (cancelled) return;
        setSession(toAuthUser(profile), body.access_token);
      } catch {
        if (!cancelled) clear();
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <>{children}</>;
}
