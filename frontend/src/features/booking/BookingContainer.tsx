import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";
import { Card, CardBody } from "../../components/ui/Card";
import { DoctorPicker } from "./DoctorPicker";
import { SlotPicker } from "./SlotPicker";
import { useBooking } from "./useBooking";
import { formatDateTimeIst } from "../../lib/format";

export function BookingContainer() {
  const { t } = useTranslation();
  const {
    pincode,
    setPincode,
    useMyLocation,
    hasLocation,
    doctors,
    doctorsLoading,
    selectedDoctorId,
    selectDoctor,
    bookSelected,
    booking,
    bookingResult,
    bookingError,
    captcha,
  } = useBooking();

  const selectedDoctor = doctors.find((d) => d.doctor_id === selectedDoctorId) ?? null;

  if (bookingResult) {
    return (
      <div className="mx-auto max-w-lg p-4">
        <Card variant="raised">
          <CardBody className="flex flex-col items-center gap-3 text-center">
            <CheckCircle2 className="h-10 w-10 text-normal" aria-hidden="true" />
            <p className="text-lg font-semibold text-fg">Appointment confirmed</p>
            <p className="text-sm text-fg-muted">{formatDateTimeIst(bookingResult.appointment.slot_start)}</p>
            <p className="text-sm text-fg">
              {t("booking.queuePosition", { position: bookingResult.queue.position ?? "—" })}
            </p>
            {bookingResult.queue.estimated_wait_minutes != null && (
              <p className="text-sm text-fg-muted">
                {t("booking.estimatedWait", { minutes: bookingResult.queue.estimated_wait_minutes })}
              </p>
            )}
            <p className="text-xs text-fg-subtle">Token: {bookingResult.queue.token}</p>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-5 px-4 py-6 sm:px-6 md:grid-cols-[2fr_1fr]">
      <DoctorPicker
        pincode={pincode}
        onPincodeChange={setPincode}
        onUseLocation={useMyLocation}
        hasLocation={hasLocation}
        doctors={doctors}
        loading={doctorsLoading}
        selectedDoctorId={selectedDoctorId}
        onSelect={selectDoctor}
      />
      <div>
        {selectedDoctor && (
          <SlotPicker
            doctor={selectedDoctor}
            captcha={captcha}
            booking={booking}
            bookingError={bookingError}
            onBook={bookSelected}
          />
        )}
      </div>
    </div>
  );
}
