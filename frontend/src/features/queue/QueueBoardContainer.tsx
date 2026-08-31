import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users, Wifi, WifiOff } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { PageHeader } from "../../components/ui/PageHeader";
import { Button } from "../../components/ui/Button";
import { Table, TableHead, TableBody, TableRow, TableHeaderCell, TableCaption } from "../../components/ui/Table";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Badge } from "../../components/ui/Badge";
import { QueueRow } from "../../components/queue/QueueRow";
import { QueueStats } from "../../components/queue/QueueStats";
import { TriageLegend } from "../../components/queue/TriageLegend";
import { getQueue, nextInQueue, escalateQueue, type QueueEntry } from "../../lib/api/endpoints/queue";
import { useAuthStore } from "../../store/auth";
import { qk } from "../../lib/queryKeys";
import { useQueueSocket } from "./useQueueSocket";
import { listVisits } from "../../lib/api/endpoints/visits";

export function QueueBoardContainer() {
  const { t } = useTranslation();
  const clinicId = useAuthStore((s) => s.user?.clinicId) ?? null;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { status } = useQueueSocket(clinicId);

  // `QueueEntryOut` carries no visit id, so map patient -> visit here to make
  // the row open the chart. Most recent visit wins; the list comes back
  // newest-first.
  const visitsQuery = useQuery({ queryKey: qk.visits(), queryFn: listVisits });
  const visitByPatient = new Map(
    [...(visitsQuery.data ?? [])].reverse().map((v) => [v.patient_id, v.id]),
  );

  const queueQuery = useQuery({
    queryKey: qk.queue(clinicId ?? "none"),
    queryFn: () => getQueue(clinicId as string),
    enabled: Boolean(clinicId),
  });

  const nextMutation = useMutation({
    mutationFn: (entryId: string) => nextInQueue(entryId),
    onMutate: async (entryId) => {
      if (!clinicId) return undefined;
      await queryClient.cancelQueries({ queryKey: qk.queue(clinicId) });
      const previous = queryClient.getQueryData<QueueEntry[]>(qk.queue(clinicId));
      queryClient.setQueryData<QueueEntry[]>(qk.queue(clinicId), (entries) =>
        (entries ?? []).filter((e) => e.id !== entryId),
      );
      return { previous };
    },
    onError: (_err, _entryId, context) => {
      if (clinicId && context?.previous) queryClient.setQueryData(qk.queue(clinicId), context.previous);
    },
    onSettled: () => {
      if (clinicId) void queryClient.invalidateQueries({ queryKey: qk.queue(clinicId) });
    },
  });

  const escalateMutation = useMutation({
    mutationFn: (entryId: string) => escalateQueue(entryId, "doctor_requested"),
    onMutate: async (entryId) => {
      if (!clinicId) return undefined;
      await queryClient.cancelQueries({ queryKey: qk.queue(clinicId) });
      const previous = queryClient.getQueryData<QueueEntry[]>(qk.queue(clinicId));
      queryClient.setQueryData<QueueEntry[]>(qk.queue(clinicId), (entries) =>
        (entries ?? []).map((e) => (e.id === entryId ? { ...e, emergency: true, position: 1 } : e)),
      );
      return { previous };
    },
    onError: (_err, _entryId, context) => {
      if (clinicId && context?.previous) queryClient.setQueryData(qk.queue(clinicId), context.previous);
    },
    onSettled: () => {
      if (clinicId) void queryClient.invalidateQueries({ queryKey: qk.queue(clinicId) });
    },
  });

  if (!clinicId) {
    return (
      <div className="page">
        <ErrorState title={t("queue.noClinic")} />
      </div>
    );
  }

  const entries = [...(queueQuery.data ?? [])].sort((a, b) => a.position - b.position);
  const headId = entries.find((e) => e.status === "waiting")?.id;

  return (
    <div className="page">
      <PageHeader
        title={t("queue.title")}
        description={t("queue.subtitle")}
        actions={
          status === "open" ? (
            <Badge tone="normal">
              <span className="relative flex h-2 w-2" aria-hidden="true">
                {/* A live board should look live: the ring only runs while the
                    socket is actually open. */}
                <span className="absolute inset-0 rounded-full bg-normal/50 animate-pulse-ring" />
                <span className="relative h-2 w-2 rounded-full bg-normal" />
              </span>
              <Wifi className="h-3 w-3" aria-hidden="true" />
              {t("queue.connected")}
            </Badge>
          ) : (
            <Badge tone="moderate">
              <WifiOff className="h-3 w-3" aria-hidden="true" />
              {t("queue.reconnecting")}
            </Badge>
          )
        }
      />

      <QueueStats entries={entries} />

      {entries.length > 0 && <TriageLegend entries={entries} />}

      {queueQuery.isLoading && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}

      {!queueQuery.isLoading && queueQuery.error && (
        <ErrorState
          title={t("errorCodes.INTERNAL")}
          action={
            <Button size="sm" variant="secondary" onClick={() => void queueQuery.refetch()}>
              {t("errors.retry")}
            </Button>
          }
        />
      )}

      {!queueQuery.isLoading && !queueQuery.error && entries.length === 0 && (
        <EmptyState
          icon={<Users className="h-6 w-6" />}
          title={t("queue.empty")}
          description={t("queue.emptyHelp", { defaultValue: "" }) || undefined}
        />
      )}

      {!queueQuery.isLoading && !queueQuery.error && entries.length > 0 && (
        <Card variant="raised" className="overflow-hidden">
          <CardHeader>
            <CardTitle subtitle={t("queue.boardSubtitle")}>{t("queue.boardTitle")}</CardTitle>
          </CardHeader>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <TableCaption>{t("queue.boardTitle")}</TableCaption>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>#</TableHeaderCell>
                  <TableHeaderCell>{t("queue.patient")}</TableHeaderCell>
                  <TableHeaderCell>{t("queue.severity")}</TableHeaderCell>
                  <TableHeaderCell>{t("queue.statusLabel")}</TableHeaderCell>
                  <TableHeaderCell>{t("queue.wait")}</TableHeaderCell>
                  <TableHeaderCell>{t("queue.token")}</TableHeaderCell>
                  <TableHeaderCell>{t("queue.actions")}</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entries.map((entry) => (
                  <QueueRow
                    key={entry.id}
                    entry={entry}
                    isHead={entry.id === headId}
                    onCallNext={(id) => nextMutation.mutate(id)}
                    onEscalate={(id) => escalateMutation.mutate(id)}
                    callingNext={nextMutation.isPending && nextMutation.variables === entry.id}
                    escalating={escalateMutation.isPending && escalateMutation.variables === entry.id}
                    onOpen={
                      visitByPatient.has(entry.patient_id)
                        ? () => navigate(`/doctor/visit/${visitByPatient.get(entry.patient_id)}`)
                        : undefined
                    }
                  />
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
