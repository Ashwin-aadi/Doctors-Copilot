import type { PreviewState } from "../PreviewPage";
import { QueueSummaryCard } from "../../doctor/QueueSummaryCard";
import { PatientListPanel } from "../../doctor/PatientListPanel";
import { PatientHeaderCard } from "../../doctor/PatientHeaderCard";
import { Dropzone } from "../../../components/upload/Dropzone";
import type { DropzoneFileState } from "../../../components/upload/uploadTypes";
import { mockPatientList, mockQueueSummary } from "../../../mocks";

const SAMPLE_FILES: Record<PreviewState, DropzoneFileState[]> = {
  loading: [{ clientId: "1", name: "cbc-report.jpg", status: "uploading", progress: 55, errorCode: null }],
  empty: [],
  error: [{ clientId: "1", name: "cbc-report.jpg", status: "error", progress: 0, errorCode: "UNREADABLE" }],
  success: [{ clientId: "1", name: "cbc-report.jpg", status: "done", progress: 100, errorCode: null }],
};

// Living reference for the doctor workspace + upload component library
// (CP2, D2.5): every screen built for that checkpoint exercises all four
// states through this one toggle.
export function StatesSection({ state }: { state: PreviewState }) {
  const queueProps =
    state === "loading"
      ? { summary: null, loading: true }
      : state === "empty"
        ? { summary: null }
        : state === "error"
          ? { summary: null, error: "Could not reach the queue service." }
          : { summary: mockQueueSummary };

  const listProps =
    state === "loading"
      ? { patients: [], loading: true }
      : state === "empty"
        ? { patients: [] }
        : state === "error"
          ? { patients: [], error: "Could not load patients." }
          : { patients: mockPatientList };

  const headerProps =
    state === "loading"
      ? { patient: null, loading: true }
      : state === "error"
        ? { patient: null, error: "Could not load this patient." }
        : state === "success"
          ? { patient: mockPatientList[0] }
          : { patient: null };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-fg-muted">Doctor dashboard</h3>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <div className="flex flex-col gap-4">
            <QueueSummaryCard {...queueProps} />
            <PatientListPanel
              {...listProps}
              selectedId={null}
              onSelect={() => {}}
              search=""
              onSearchChange={() => {}}
              filters={{ colours: [], severities: [] }}
              onFilterChange={() => {}}
            />
          </div>
          <PatientHeaderCard {...headerProps} />
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-fg-muted">Report upload</h3>
        <Dropzone files={SAMPLE_FILES[state]} onFilesSelected={() => {}} onCancel={() => {}} onRetry={() => {}} />
      </div>
    </div>
  );
}
