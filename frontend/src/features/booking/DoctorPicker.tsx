import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { MapPin, Star } from "lucide-react";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { formatInr, formatKm } from "../../lib/format";
import type { DoctorRanked } from "../../lib/api/endpoints/doctors";

export interface DoctorPickerProps {
  pincode: string;
  onPincodeChange: (value: string) => void;
  onUseLocation: () => void;
  hasLocation: boolean;
  doctors: DoctorRanked[];
  loading: boolean;
  selectedDoctorId: string | null;
  onSelect: (doctorId: string) => void;
  /** Booking panel for the selected doctor, rendered inside that doctor's own
   *  card. A panel parked outside the list makes the reader match a name in
   *  one column against a name in another; here it is beside the doctor it
   *  books. Returns null for every other row. */
  renderBookingPanel?: (doctor: DoctorRanked) => ReactNode;
}

export function DoctorPicker({
  pincode,
  onPincodeChange,
  onUseLocation,
  hasLocation,
  doctors,
  loading,
  selectedDoctorId,
  onSelect,
  renderBookingPanel,
}: DoctorPickerProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-fg">{t("booking.pincodeLabel")}</span>
          <Input
            inputMode="numeric"
            maxLength={6}
            placeholder={t("booking.pincodePlaceholder")}
            value={pincode}
            onChange={(e) => onPincodeChange(e.target.value.replace(/\D/g, ""))}
          />
        </label>
        <Button type="button" variant="secondary" leftIcon={<MapPin className="h-4 w-4" />} onClick={onUseLocation}>
          {t("booking.useLocation")}
        </Button>
      </div>
      {!hasLocation && <p className="text-xs text-fg-subtle">{t("booking.locationNote")}</p>}

      {loading && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {!loading && doctors.length === 0 && (
        <EmptyState title="No doctors found" description="Try a different specialty or location." />
      )}

      <div className="flex flex-col gap-3">
        {doctors.map((doctor) => {
          const selected = selectedDoctorId === doctor.doctor_id;
          // The panel is a sibling of the select button, never a child: its
          // own button and captcha input cannot be nested inside one.
          const panel = selected ? renderBookingPanel?.(doctor) : null;

          return (
            <Card key={doctor.doctor_id} variant={selected ? "raised" : "flat"} className="p-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-start">
                <button
                  type="button"
                  onClick={() => onSelect(doctor.doctor_id)}
                  aria-pressed={selected}
                  className="flex min-w-0 flex-1 cursor-pointer flex-col gap-2 text-left"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-fg">{doctor.name}</p>
                      <p className="text-sm text-fg-muted">
                        {doctor.specialty} · {doctor.clinic_name}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1 text-sm text-fg-muted">
                      <Star className="h-4 w-4 text-high" aria-hidden="true" />
                      {doctor.rating.toFixed(1)}
                    </div>
                  </div>
                  {doctor.nmc_reg_no && (
                    <p className="text-xs text-fg-subtle">{t("booking.nmc")}: {doctor.nmc_reg_no}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-3 text-sm text-fg-muted">
                    <span>{t("booking.distance", { km: formatKm(doctor.distance_km) })}</span>
                    <span>{formatInr(doctor.fee)}</span>
                  </div>
                  {doctor.reasons.length > 0 && (
                    <ul className="list-inside list-disc text-xs text-fg-subtle">
                      {doctor.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  )}
                </button>
                {panel}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
