import { TagInput } from "../../../components/forms/TagInput";
import type { StepProps } from "../types";

const CONDITION_SUGGESTIONS = [
  "Type 2 diabetes", "Hypertension", "Tuberculosis (past)", "Asthma", "COPD",
  "Rheumatic heart disease", "Anaemia", "Thyroid disorder",
];
const ALLERGY_SUGGESTIONS = ["Penicillin", "Sulfa drugs", "Peanuts", "Dust", "NSAIDs"];
const MEDICATION_SUGGESTIONS = ["Metformin", "Amlodipine", "Levothyroxine", "Salbutamol inhaler"];

export function HistoryStep({ values, onChange }: StepProps) {
  return (
    <div className="flex flex-col gap-4">
      <TagInput
        label="Existing conditions"
        values={values.conditions}
        onChange={(v) => onChange("conditions", v)}
        suggestions={CONDITION_SUGGESTIONS}
        placeholder="Type and press Enter"
      />
      <TagInput
        label="Allergies"
        values={values.allergies}
        onChange={(v) => onChange("allergies", v)}
        suggestions={ALLERGY_SUGGESTIONS}
        placeholder="Type and press Enter"
      />
      <TagInput
        label="Current medications"
        values={values.medications}
        onChange={(v) => onChange("medications", v)}
        suggestions={MEDICATION_SUGGESTIONS}
        placeholder="Type and press Enter"
      />
    </div>
  );
}
