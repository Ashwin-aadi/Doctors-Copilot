import { useTranslation } from "react-i18next";
import { Card, CardBody } from "../ui/Card";
import type { QueueEntry } from "../../lib/api/endpoints/queue";

interface QueueStatsProps {
  entries: QueueEntry[];
}

export function QueueStats({ entries }: QueueStatsProps) {
  const { t } = useTranslation();
  const waiting = entries.filter((e) => e.status === "waiting").length;
  const inConsult = entries.filter((e) => e.status === "in_consult").length;
  const avgWait =
    waiting > 0
      ? Math.round(entries.filter((e) => e.status === "waiting").reduce((sum, e) => sum + e.estimated_wait_minutes, 0) / waiting)
      : 0;

  return (
    <div className="grid grid-cols-3 gap-3">
      <Card>
        <CardBody className="p-3 text-center">
          <p className="text-2xl font-semibold text-fg">{waiting}</p>
          <p className="text-xs text-fg-muted">{t("queue.waitingCount")}</p>
        </CardBody>
      </Card>
      <Card>
        <CardBody className="p-3 text-center">
          <p className="text-2xl font-semibold text-fg">{inConsult}</p>
          <p className="text-xs text-fg-muted">{t("queue.inConsultCount")}</p>
        </CardBody>
      </Card>
      <Card>
        <CardBody className="p-3 text-center">
          <p className="text-2xl font-semibold text-fg">{avgWait}</p>
          <p className="text-xs text-fg-muted">{t("queue.avgWaitMinutes")}</p>
        </CardBody>
      </Card>
    </div>
  );
}
