import type { ReactNode } from "react";
import { Stethoscope, ShieldCheck, MapPin, Activity } from "lucide-react";

export interface AuthLayoutProps {
  children: ReactNode;
}

/**
 * A single ECG cycle, drawn once and repeated across the panel.
 *
 * It is decorative -- it carries no reading -- but it is the one place in the
 * product where a picture belongs: the sign-in panel has nothing else to say
 * about what the tool is for, and a clinical trace says it in a glance.
 */
function EcgTrace() {
  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 bottom-24 h-32 w-full opacity-20"
      viewBox="0 0 600 100"
      preserveAspectRatio="none"
      fill="none"
    >
      <path
        d="M0 60 H60 l12 0 8 -34 10 62 9 -28 12 0 H190 l12 0 8 -34 10 62 9 -28 12 0 H320 l12 0 8 -34 10 62 9 -28 12 0 H450 l12 0 8 -34 10 62 9 -28 12 0 H600"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-primary p-10 text-primary-fg md:flex">
        {/* Two soft washes over the flat fill so the panel has depth without
            introducing a second brand colour. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-24 h-80 w-80 rounded-full bg-white/10 blur-3xl"
        />
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-32 -right-16 h-96 w-96 rounded-full bg-black/15 blur-3xl"
        />
        <EcgTrace />

        <div className="relative flex items-center gap-2 text-lg font-semibold">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/15 ring-1 ring-inset ring-white/20">
            <Stethoscope className="h-5 w-5" aria-hidden="true" />
          </span>
          Doctor&apos;s Copilot
        </div>

        <div className="relative flex flex-col gap-6">
          <h1 className="animate-slide-up text-3xl font-semibold leading-tight">
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
            <li className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white/12 ring-1 ring-inset ring-white/20">
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              </span>
              Consent handled under the DPDP Act, 2023
            </li>
            <li className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white/12 ring-1 ring-inset ring-white/20">
                <MapPin className="h-4 w-4" aria-hidden="true" />
              </span>
              Works with your ABHA ID — no new health ID required
            </li>
            <li className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white/12 ring-1 ring-inset ring-white/20">
                <Activity className="h-4 w-4" aria-hidden="true" />
              </span>
              MoHFW colour triage — Red, Yellow, Green — on every visit
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-primary-fg/70">
          Medical emergency? Call <strong>112</strong>, or <strong>108</strong> for an ambulance.
        </p>
      </div>

      <div className="flex items-center justify-center bg-bg p-6">
        <div className="w-full max-w-[420px] animate-slide-up">{children}</div>
      </div>
    </div>
  );
}
