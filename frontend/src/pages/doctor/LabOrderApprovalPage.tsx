import { useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { formatInr } from "../../lib/format";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { CardSkeleton } from "../../components/ui/states/CardSkeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { EmptyState } from "../../components/ui/EmptyState";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Modal } from "../../components/ui/Modal";
import { FormError } from "../../components/forms/FormError";
import { CaptchaWidget, type CaptchaChallenge } from "../../components/forms/CaptchaWidget";
import { LabOrderItemRow } from "./LabOrderItemRow";
import { LockedRecordBanner } from "./LockedRecordBanner";
import type { LabCatalogItem, LabOrderDiff, LabOrderItem, LabOrderOut } from "../../components/types";

export interface LabOrderApprovalPageProps {
  order: LabOrderOut | null;
  originalRecommendation?: LabOrderItem[];
  catalog: LabCatalogItem[];
  approverName?: string;
  approverNmc?: string;
  /** `LabOrderOut` (GET) doesn't carry `content_hash` -- only the approve
   * mutation response does. The container passes it through once known. */
  contentHash?: string;
  onChange: (items: LabOrderItem[]) => void;
  onApprove: (captchaToken: string) => void;
  captchaChallenge: CaptchaChallenge | null;
  onCaptchaToken: (token: string) => void;
  onCaptchaRefresh: () => void;
  approving?: boolean;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

function costFor(item: LabOrderItem, catalog: LabCatalogItem[]): number {
  return catalog.find((c) => c.name === item.name)?.costInr ?? 0;
}

function diffFor(item: LabOrderItem, original: LabOrderItem[] | undefined): LabOrderDiff {
  if (!original) return null;
  return original.some((o) => o.name === item.name) ? null : "added";
}

export function LabOrderApprovalPage({
  order,
  originalRecommendation,
  catalog,
  approverName,
  approverNmc,
  contentHash,
  onChange,
  onApprove,
  captchaChallenge,
  onCaptchaToken,
  onCaptchaRefresh,
  approving,
  loading,
  error,
  onRetry,
}: LabOrderApprovalPageProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [addQuery, setAddQuery] = useState("");

  const total = useMemo(
    () => (order ? order.items.reduce((sum, item) => sum + costFor(item, catalog), 0) : 0),
    [order, catalog],
  );

  const removed = useMemo(
    () =>
      order && originalRecommendation
        ? originalRecommendation.filter((o) => !order.items.some((i) => i.name === o.name))
        : [],
    [order, originalRecommendation],
  );

  if (loading) return <CardSkeleton />;

  if (error) {
    return (
      <ErrorState
        title="Couldn't load this lab order"
        description={error}
        action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
      />
    );
  }

  if (!order) {
    return (
      <Card>
        <CardBody>
          <EmptyState title="No lab order selected" />
        </CardBody>
      </Card>
    );
  }

  function removeItem(name: string) {
    if (!order) return;
    onChange(order.items.filter((i) => i.name !== name));
  }

  function addItem() {
    if (!order || !addQuery.trim()) return;
    const catalogEntry = catalog.find((c) => c.name.toLowerCase() === addQuery.trim().toLowerCase());
    if (!catalogEntry || order.items.some((i) => i.name === catalogEntry.name)) return;
    onChange([
      ...order.items,
      {
        name: catalogEntry.name,
        loinc: catalogEntry.loinc ?? null,
        reason: catalogEntry.defaultReason,
        source: "rag",
        cghs_code: catalogEntry.cghsCode ?? null,
        pmjay_package: catalogEntry.pmjayPackage ?? null,
      },
    ]);
    setAddQuery("");
  }

  function handleApproveConfirm() {
    if (!captchaToken) return;
    onApprove(captchaToken);
  }

  return (
    <Card variant="raised">
      <CardHeader>
        <CardTitle>Lab order</CardTitle>
        {order.locked ? <Badge tone="normal">Approved</Badge> : <Badge tone="moderate">Draft</Badge>}
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        {order.locked && approverName && approverNmc && order.approved_at && (
          <LockedRecordBanner
            approverName={approverName}
            nmcRegNo={approverNmc}
            approvedAt={order.approved_at}
            contentHash={contentHash ?? order.id}
          />
        )}

        <ul role="list" aria-label="Recommended tests" className="flex flex-col gap-2" data-testid="lab-order-items">
          {order.items.length === 0 && <EmptyState title="No tests recommended yet" />}
          {order.items.map((item) => (
            <LabOrderItemRow
              key={item.name}
              item={item}
              costInr={costFor(item, catalog)}
              locked={order.locked}
              diff={diffFor(item, originalRecommendation)}
              onRemove={order.locked ? undefined : () => removeItem(item.name)}
            />
          ))}
          {!order.locked &&
            removed.map((item) => (
              <LabOrderItemRow key={`removed-${item.name}`} item={item} costInr={costFor(item, catalog)} locked diff="removed" />
            ))}
        </ul>

        {!order.locked && (
          <div className="flex items-center gap-2">
            <Input
              list="lab-catalog"
              placeholder="Add a test…"
              aria-label="Add a test from the catalogue"
              value={addQuery}
              onChange={(e) => setAddQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addItem()}
            />
            <datalist id="lab-catalog">
              {catalog.map((c) => (
                <option key={c.name} value={c.name} />
              ))}
            </datalist>
            <Button type="button" size="sm" variant="secondary" onClick={addItem}>
              Add
            </Button>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-border pt-3">
          <span className="text-sm text-fg-muted">Order total</span>
          <span className="text-lg font-semibold tabular-nums text-fg">{formatInr(total)}</span>
        </div>

        {!order.locked && (
          <Button onClick={() => setModalOpen(true)} leftIcon={<ShieldCheck className="h-4 w-4" />}>
            Approve lab order
          </Button>
        )}
      </CardBody>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Verify to approve"
        footer={
          <Button onClick={handleApproveConfirm} disabled={!captchaToken} loading={approving}>
            Confirm approval
          </Button>
        }
      >
        <CaptchaWidget
          challenge={captchaChallenge}
          onToken={(token) => {
            setCaptchaToken(token);
            onCaptchaToken(token);
          }}
          onRefresh={() => {
            setCaptchaToken(null);
            onCaptchaRefresh();
          }}
        />
        <FormError message={error ?? null} />
      </Modal>
    </Card>
  );
}
