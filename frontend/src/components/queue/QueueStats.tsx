import { useTranslation } from "react-i18next";
import { AlertTriangle, Clock, Stethoscope, Users } from "lucide-react";
import { StatTile } from "../ui/StatTile";
import type { QueueEntry } from "../../lib/api/endpoints/queue";

interface QueueStatsProps {
  entries: QueueEntry[];
}

export function QueueStats({ entries }: QueueStatsProps) {
  const { t } = useTranslation();
  const waitingEntries = entries.filter((e) => e.status === "waiting");
  const waiting = waitingEntries.length;
  const inConsult = entries.filter((e) => e.status === "in_consult").length;
  const avgWait =
    waiting > 0
      ? Math.round(
          waitingEntries.reduce((sum, e) => sum + e.estimated_wait_minutes, 0) / waiting,
        )
      : 0;
  // Red-coded and escalated entries are the reason a charge nurse looks at this
  // board at all, so they get a tile rather than only a row colour.
  const urgent = entries.filter(
    (e) => e.status !== "done" && (e.emergency || e.triage_colour === "red"),
  ).length;

  return (
    <div className="stagger grid grid-cols-2 gap-3 xl:grid-cols-4">
      <StatTile
        label={t("queue.waitingCount")}
        value={waiting}
        tone="primary"
        icon={<Users className="h-[18px] w-[18px]" />}
      />
      <StatTile
        label={t("queue.inConsultCount")}
        value={inConsult}
        tone="info"
        icon={<Stethoscope className="h-[18px] w-[18px]" />}
      />
      <StatTile
        label={t("queue.avgWaitMinutes")}
        value={avgWait}
        hint={t("queue.minutesHint")}
        tone={avgWait >= 45 ? "high" : "neutral"}
        icon={<Clock className="h-[18px] w-[18px]" />}
      />
      <StatTile
        label={t("queue.urgentCount")}
        value={urgent}
        tone={urgent > 0 ? "critical" : "normal"}
        icon={<AlertTriangle className="h-[18px] w-[18px]" />}
      />
    </div>
  );
}
