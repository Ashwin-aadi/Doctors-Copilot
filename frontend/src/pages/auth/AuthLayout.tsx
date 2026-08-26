import type { ReactNode } from "react";
import { Stethoscope, ShieldCheck, MapPin } from "lucide-react";

export interface AuthLayoutProps {
  children: ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-primary p-10 text-primary-fg md:flex">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <Stethoscope className="h-6 w-6" aria-hidden="true" />
          Doctor&apos;s Copilot
        </div>
        <div className="flex flex-col gap-6">
          <h1 className="text-3xl font-semibold leading-tight">
            Shorter OPD queues.
            <br />
            Clearer clinical decisions.
          </h1>
          <p className="max-w-sm text-sm text-primary-fg/85">
            Built for Indian primary and secondary care — triage grounded in ICMR and MoHFW
            guidance, generic medicines flagged against the NLEM and Jan Aushadhi Kendras, and
            every clinical approval locked behind a doctor&apos;s signature.
          </p>
          <ul className="flex flex-col gap-3 text-sm text-primary-fg/85">
            <li className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
              Consent handled under the DPDP Act, 2023
            </li>
            <li className="flex items-center gap-2">
              <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
              Works with your ABHA ID — no new health ID required
            </li>
          </ul>
        </div>
        <p className="text-xs text-primary-fg/70">
          Medical emergency? Call <strong>112</strong>, or <strong>108</strong> for an ambulance.
        </p>
      </div>

      <div className="flex items-center justify-center bg-bg p-6">
        <div className="w-full max-w-[420px]">{children}</div>
      </div>
    </div>
  );
}
