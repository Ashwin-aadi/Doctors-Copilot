import { QueueSummaryCard } from "./QueueSummaryCard";
import { PatientListPanel, type PatientListFilters } from "./PatientListPanel";
import { PatientHeaderCard } from "./PatientHeaderCard";
import type { PatientListItem, QueueSummary } from "../../components/types";

export interface DoctorDashboardPageProps {
  queueSummary: QueueSummary | null;
  queueLoading?: boolean;
  queueError?: string | null;
  onRetryQueue?: () => void;

  patients: PatientListItem[];
  patientsLoading?: boolean;
  patientsError?: string | null;
  onRetryPatients?: () => void;

  selectedPatientId: string | null;
  onSelectPatient: (id: string) => void;

  search: string;
  onSearchChange: (value: string) => void;
  filters: PatientListFilters;
  onFilterChange: (filters: PatientListFilters) => void;

  selectedPatient: PatientListItem | null;
  selectedPatientLoading?: boolean;
  selectedPatientError?: string | null;
  onRetrySelectedPatient?: () => void;
}

// Pure composition of the presentational pieces below -- all data arrives
// via props from a data-fetching container owned elsewhere.
export function DoctorDashboardPage({
  queueSummary,
  queueLoading,
  queueError,
  onRetryQueue,
  patients,
  patientsLoading,
  patientsError,
  onRetryPatients,
  selectedPatientId,
  onSelectPatient,
  search,
  onSearchChange,
  filters,
  onFilterChange,
  selectedPatient,
  selectedPatientLoading,
  selectedPatientError,
  onRetrySelectedPatient,
}: DoctorDashboardPageProps) {
  return (
    <div className="flex flex-col gap-4 p-4 lg:grid lg:grid-cols-[2fr_1fr] lg:items-start lg:gap-4">
      <div className="flex flex-col gap-4">
        <QueueSummaryCard summary={queueSummary} loading={queueLoading} error={queueError} onRetry={onRetryQueue} />
        <PatientListPanel
          patients={patients}
          selectedId={selectedPatientId}
          onSelect={onSelectPatient}
          search={search}
          onSearchChange={onSearchChange}
          filters={filters}
          onFilterChange={onFilterChange}
          loading={patientsLoading}
          error={patientsError}
          onRetry={onRetryPatients}
        />
      </div>
      <PatientHeaderCard
        patient={selectedPatient}
        loading={selectedPatientLoading}
        error={selectedPatientError}
        onRetry={onRetrySelectedPatient}
      />
    </div>
  );
}
