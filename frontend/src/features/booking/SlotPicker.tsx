import { useTranslation } from "react-i18next";
import { Card, CardBody } from "../../components/ui/Card";
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

export function SlotPicker({ doctor, captcha, booking, bookingError, onBook }: SlotPickerProps) {
  const { t } = useTranslation();

  return (
    <Card variant="raised">
      <CardBody className="flex flex-col gap-4">
        <div>
          <p className="font-medium text-fg">{doctor.name}</p>
          <p className="text-sm text-fg-muted">{formatDateTimeIst(doctor.next_slot)}</p>
        </div>
        {captcha.enabled && (
          <CaptchaWidget challenge={captcha.challenge} onToken={captcha.onToken} onRefresh={captcha.onRefresh} />
        )}
        <FormError message={bookingError ?? undefined} />
        <Button onClick={onBook} loading={booking} disabled={captcha.enabled && !captcha.token}>
          {t("booking.book")}
        </Button>
      </CardBody>
    </Card>
  );
}
