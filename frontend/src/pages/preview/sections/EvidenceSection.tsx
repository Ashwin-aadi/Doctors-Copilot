import { useState } from "react";
import { Button } from "../../../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../../../components/ui/Card";
import { CopilotPanel } from "../../doctor/CopilotPanel";
import { SourceCard } from "../../../components/citations/SourceCard";
import { EvidenceDrawer } from "../../../components/citations/EvidenceDrawer";
import { ConfidenceMeter } from "../../../components/citations/ConfidenceMeter";
import { EmergencyBanner } from "../../../components/alerts/EmergencyBanner";
import { ScheduleWarning } from "../../../components/alerts/ScheduleWarning";
import { mockCopilotBrief } from "../../../mocks/mockCopilotBrief";
import { mockInteractionReport } from "../../../mocks/mockInteractionReport";
import type { PreviewState } from "../PreviewPage";
import type { Citation } from "../../../components/types";

const whoCitation: Citation = {
  n: 2,
  title: "Dengue and severe dengue",
  source: "WHO",
  url: "https://www.who.int/news-room/fact-sheets/detail/dengue",
  snippet: "Severe dengue is a potentially fatal complication due to plasma leaking.",
  published: "2024",
};

const mixedCitations = [...mockCopilotBrief.citations, whoCitation];

export function EvidenceSection({ state }: { state: PreviewState }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);

  const loading = state === "loading";
  const error = state === "error" ? "The model was unreachable. Try again in a moment." : null;
  const brief = state === "empty" ? null : { ...mockCopilotBrief, citations: mixedCitations };

  return (
    <div className="flex flex-col gap-4">
      <EmergencyBanner onFindClinic={() => undefined} />

      <CopilotPanel
        brief={brief}
        safety={state === "empty" ? null : mockInteractionReport}
        loading={loading}
        error={error}
        acknowledgedPairs={acknowledged}
        onAcknowledge={(a, b) => setAcknowledged((prev) => [...prev, [a, b].sort().join("|")])}
        onCitationClick={() => setDrawerOpen(true)}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Provenance ranking</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-2">
          {mixedCitations.map((c) => (
            <SourceCard key={c.n} citation={c} />
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Confidence bands</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          <ConfidenceMeter value={0.22} />
          <ConfidenceMeter value={0.55} />
          <ConfidenceMeter value={0.88} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Statutory schedule warnings</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-2">
          <ScheduleWarning drug="Metformin (Glycomet)" schedule="H" />
          <ScheduleWarning drug="Alprazolam (Alprax)" schedule="H1" />
        </CardBody>
      </Card>

      <Button variant="secondary" className="w-fit" onClick={() => setDrawerOpen(true)}>
        Open evidence drawer
      </Button>

      <EvidenceDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        citations={mixedCitations}
      />
    </div>
  );
}
