import { useTranslation } from "react-i18next";
import { Button } from "../../components/ui/Button";
import { FormError } from "../../components/forms/FormError";
import { CaptchaWidget } from "../../components/forms/CaptchaWidget";
import { formatDateTimeIst } from "../../lib/format";
import type { DoctorRanked } from "../../lib/api/endpoints/doctors";
import type { UseCaptchaResult } from "../../hooks/useCaptcha";

export interface SlotPickerProps {
  doctor: DoctorRanked;
  captcha: UseCaptchaResult;
  booking: boolean;
  bookingError: string | null;
  onBook: () => void;
}

/** Booking panel for one doctor. Rendered inside that doctor's card in the
 *  results list, so it sits beside the name it belongs to -- it carries no
 *  surface of its own and never repeats the doctor's name.
 */
export function SlotPicker({ doctor, captcha, booking, bookingError, onBook }: SlotPickerProps) {
  const { t } = useTranslation();

  return (
    <div className="flex shrink-0 flex-col gap-3 border-t border-border pt-4 md:w-60 md:border-l md:border-t-0 md:pl-4 md:pt-0">
      <div>
        <p className="text-xs uppercase tracking-wide text-fg-subtle">{t("booking.nextSlot")}</p>
        <p className="text-sm font-medium text-fg">{formatDateTimeIst(doctor.next_slot)}</p>
      </div>
      {captcha.enabled && (
        <CaptchaWidget challenge={captcha.challenge} onToken={captcha.onToken} onRefresh={captcha.onRefresh} />
      )}
      <FormError message={bookingError ?? undefined} />
      <Button onClick={onBook} loading={booking} disabled={captcha.enabled && !captcha.token}>
        {t("booking.book")}
      </Button>
    </div>
  );
}
