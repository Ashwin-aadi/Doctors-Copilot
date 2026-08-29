import { useTranslation } from "react-i18next";
import { Plus, Save, Trash2 } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Input } from "../../components/ui/Input";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { FormError } from "../../components/forms/FormError";
import { ApiError } from "../../lib/api/errors";
import { MedSuggestionsCard } from "./MedSuggestions";
import { usePrescriptionDraft } from "./usePrescriptionDraft";

export interface PrescriptionEditorProps {
  visitId: string;
  patientConditions?: string[];
  patientAllergies?: string[];
  patientMedications?: string[];
}

/**
 * The doctor's prescription pad: add, edit and remove medicines, then save.
 *
 * Suggestions sit beside the pad rather than inside it -- a candidate becomes
 * a prescribed medicine only when the doctor puts it there, and the dose,
 * frequency and duration are always theirs to write.
 */
export function PrescriptionEditor({
  visitId,
  patientConditions = [],
  patientAllergies = [],
  patientMedications = [],
}: PrescriptionEditorProps) {
  const { t } = useTranslation();
  const draft = usePrescriptionDraft(visitId);

  if (draft.loading) {
    return (
      <Card>
        <CardBody className="flex flex-col gap-2">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-24 w-full" />
        </CardBody>
      </Card>
    );
  }

  const alreadyOnPad = (name: string) =>
    draft.draft.some((item) => item.name.trim().toLowerCase() === name.trim().toLowerCase());

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("prescriptionEditor.title")}</CardTitle>
          <div className="flex items-center gap-2">
            {draft.locked && <Badge tone="normal">{t("prescriptionEditor.signed")}</Badge>}
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Plus className="h-4 w-4" />}
              disabled={draft.locked}
              data-testid="add-medicine"
              onClick={() => draft.add()}
            >
              {t("prescriptionEditor.addRow")}
            </Button>
            <Button
              size="sm"
              leftIcon={<Save className="h-4 w-4" />}
              loading={draft.saving}
              disabled={draft.locked}
              data-testid="save-prescription"
              onClick={() => draft.save()}
            >
              {t("prescriptionEditor.save")}
            </Button>
          </div>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          {draft.locked && (
            <p className="text-xs text-fg-subtle">{t("prescriptionEditor.lockedHelp")}</p>
          )}

          {draft.draft.length === 0 && (
            <EmptyState
              title={t("prescriptionEditor.empty")}
              description={t("prescriptionEditor.emptyHelp")}
            />
          )}

          {draft.draft.map((item, index) => (
            <div
              key={index}
              data-testid="prescription-row"
              className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-[2fr_1fr_1fr_1fr_auto]"
            >
              <Input
                size="sm"
                aria-label={t("prescriptionEditor.medicine")}
                placeholder={t("prescriptionEditor.medicine")}
                value={item.name}
                disabled={draft.locked}
                onChange={(e) => draft.update(index, "name", e.target.value)}
              />
              <Input
                size="sm"
                aria-label={t("prescriptionEditor.dose")}
                placeholder={t("prescriptionEditor.dose")}
                value={item.dose ?? ""}
                disabled={draft.locked}
                onChange={(e) => draft.update(index, "dose", e.target.value)}
              />
              <Input
                size="sm"
                aria-label={t("prescriptionEditor.frequency")}
                placeholder={t("prescriptionEditor.frequency")}
                value={item.frequency ?? ""}
                disabled={draft.locked}
                onChange={(e) => draft.update(index, "frequency", e.target.value)}
              />
              <Input
                size="sm"
                aria-label={t("prescriptionEditor.duration")}
                placeholder={t("prescriptionEditor.duration")}
                value={item.duration ?? ""}
                disabled={draft.locked}
                onChange={(e) => draft.update(index, "duration", e.target.value)}
              />
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<Trash2 className="h-4 w-4" />}
                disabled={draft.locked}
                aria-label={t("prescriptionEditor.removeRow", { name: item.name })}
                onClick={() => draft.remove(index)}
              >
                {t("prescriptionEditor.remove")}
              </Button>
            </div>
          ))}

          {draft.saveError != null && (
            <FormError
              message={
                draft.saveError instanceof ApiError
                  ? t(`errorCodes.${draft.saveError.code}`, {
                      defaultValue: t("errorCodes.INTERNAL"),
                    })
                  : t("errorCodes.INTERNAL")
              }
            />
          )}
          {draft.saved && !draft.saving && (
            <p className="text-xs text-normal" data-testid="prescription-saved">
              {t("prescriptionEditor.saved")}
            </p>
          )}
        </CardBody>
      </Card>

      {!draft.locked && (
        <MedSuggestionsCard
          visitId={visitId}
          conditions={patientConditions}
          allergies={patientAllergies}
          currentMedications={patientMedications}
          onAdd={(candidate) =>
            draft.add({
              name: candidate.name,
              dose: "",
              frequency: "",
              duration: "",
              notes: candidate.rationale,
            })
          }
          isAdded={alreadyOnPad}
        />
      )}
    </div>
  );
}
