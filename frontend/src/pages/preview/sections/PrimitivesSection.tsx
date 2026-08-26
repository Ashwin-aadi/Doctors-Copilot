import { useState } from "react";
import { Search, Trash2 } from "lucide-react";
import {
  Button,
  Input,
  Select,
  Textarea,
  Checkbox,
  Radio,
  Switch,
  Card,
  CardHeader,
  CardTitle,
  CardBody,
  Modal,
  Drawer,
  Tabs,
  Badge,
  SeverityPill,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  TableCaption,
  useToast,
  Skeleton,
  EmptyState,
  ErrorState,
  Tooltip,
  Stepper,
  Spinner,
  Avatar,
  Divider,
} from "../../../components/ui";
import type { PreviewState } from "../PreviewPage";

export function PrimitivesSection({ state }: { state: PreviewState }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState("overview");
  const [switchOn, setSwitchOn] = useState(true);
  const { push } = useToast();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
        <Button variant="link">Link action</Button>
        <Button loading>Saving</Button>
        <Button leftIcon={<Search className="h-4 w-4" />}>With icon</Button>
        <Button variant="danger" size="sm" leftIcon={<Trash2 className="h-4 w-4" />}>
          Remove
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input aria-label="Patient name" placeholder="Patient name" className="w-48" />
        <Select
          aria-label="State"
          placeholder="Select state"
          options={[
            { value: "mh", label: "Maharashtra" },
            { value: "dl", label: "Delhi" },
            { value: "ka", label: "Karnataka" },
          ]}
          className="w-48"
        />
        <Textarea aria-label="Notes" placeholder="Clinical notes" className="w-64" rows={2} />
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Checkbox label="Fever" onChange={() => {}} defaultChecked />
        <Radio label="Male" name="sex-preview" onChange={() => {}} defaultChecked />
        <Radio label="Female" name="sex-preview" onChange={() => {}} />
        <Switch checked={switchOn} onChange={setSwitchOn} label="SMS reminders" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="primary">Verified</Badge>
        <Badge tone="accent">Jan Aushadhi</Badge>
        <SeverityPill esi={1} />
        <SeverityPill esi={3} />
        <SeverityPill esi={5} />
        <SeverityPill level="critical" />
        <Avatar name="Ananya Sharma" />
        <Tooltip content="National Medical Commission registration">
          <Badge tone="info">NMC 12345</Badge>
        </Tooltip>
      </div>

      <Stepper
        steps={[
          { key: "triage", label: "Triage" },
          { key: "labs", label: "Labs" },
          { key: "brief", label: "Brief" },
          { key: "consult", label: "Consult" },
        ]}
        currentKey="labs"
      />

      <Divider label="Interactive" />

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => setModalOpen(true)}>Open modal</Button>
        <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
          Open drawer
        </Button>
        <Button
          variant="ghost"
          onClick={() => push({ title: "Lab order approved", tone: "success" })}
        >
          Fire toast
        </Button>
        <Spinner />
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Approve lab order">
        <p className="text-sm text-fg-muted">This mirrors the doctor approval flow with captcha.</p>
      </Modal>
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Evidence">
        <p className="text-sm text-fg-muted">Citation drawer content goes here.</p>
      </Drawer>

      <Tabs
        items={[
          { value: "overview", label: "Overview" },
          { value: "history", label: "History" },
        ]}
        value={tab}
        onChange={setTab}
      >
        <p className="text-sm text-fg-muted">Tab panel: {tab}</p>
      </Tabs>

      <Card>
        <CardHeader>
          <CardTitle>Recent lab results</CardTitle>
          <Badge tone="normal">Up to date</Badge>
        </CardHeader>
        <CardBody>
          {state === "loading" && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          )}
          {state === "empty" && (
            <EmptyState title="No lab results yet" description="Reports will appear here once uploaded." />
          )}
          {state === "error" && (
            <ErrorState
              title="Could not load lab results"
              description="Check your connection and try again."
              action={<Button size="sm">Retry</Button>}
            />
          )}
          {state === "success" && (
            <Table>
              <TableCaption>Recent lab results</TableCaption>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Test</TableHeaderCell>
                  <TableHeaderCell>Value</TableHeaderCell>
                  <TableHeaderCell>Flag</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow zebra>
                  <TableCell>Haemoglobin</TableCell>
                  <TableCell>9.2 g/dL</TableCell>
                  <TableCell>
                    <SeverityPill level="high" />
                  </TableCell>
                </TableRow>
                <TableRow zebra>
                  <TableCell>Platelet count</TableCell>
                  <TableCell>142,000 /µL</TableCell>
                  <TableCell>
                    <SeverityPill level="normal" />
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
