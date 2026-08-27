import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import { Lock } from "lucide-react";

dayjs.extend(utc);
dayjs.extend(timezone);

export interface LockedRecordBannerProps {
  approverName: string;
  nmcRegNo: string;
  approvedAt: string;
  contentHash: string;
}

function formatIst24(value: string): string {
  return dayjs(value).tz("Asia/Kolkata").format("DD/MM/YYYY HH:mm");
}

function truncateHash(hash: string): string {
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-8)}`;
}

export function LockedRecordBanner({ approverName, nmcRegNo, approvedAt, contentHash }: LockedRecordBannerProps) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-normal/30 bg-normal-soft p-3 text-sm text-fg">
      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-normal" aria-hidden="true" />
      <div className="flex flex-col gap-0.5">
        <p className="font-medium">
          Approved by {approverName} <span className="text-fg-muted">(NMC {nmcRegNo})</span>
        </p>
        <p className="text-xs text-fg-muted">{formatIst24(approvedAt)} IST</p>
        <p className="font-mono text-xs text-fg-subtle" title={contentHash}>
          Hash: {truncateHash(contentHash)}
        </p>
        <p className="mt-1 text-xs text-fg-muted">Locked — create an amendment instead.</p>
      </div>
    </div>
  );
}
