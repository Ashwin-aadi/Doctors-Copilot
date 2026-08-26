import { FormField } from "../../../components/forms/FormField";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import type { StepProps } from "../types";

const INDIAN_STATES = [
  "Andhra Pradesh", "Bihar", "Delhi", "Gujarat", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Punjab", "Rajasthan", "Tamil Nadu",
  "Telangana", "Uttar Pradesh", "West Bengal",
];

export function ContactStep({ values, errors, onChange }: StepProps) {
  return (
    <div className="flex flex-col gap-4">
      <FormField label="Mobile number" error={errors.phone} required>
        <div className="flex items-center gap-2">
          <span className="flex h-10 items-center rounded-md border border-border bg-surface-2 px-3 text-sm text-fg-muted">
            +91
          </span>
          <Input
            type="tel"
            inputMode="numeric"
            maxLength={10}
            value={values.phone}
            onChange={(e) => onChange("phone", e.target.value.replace(/\D/g, ""))}
            placeholder="98765 43210"
          />
        </div>
      </FormField>

      <FormField label="Address" error={errors.address}>
        <Input
          value={values.address}
          onChange={(e) => onChange("address", e.target.value)}
          placeholder="House / street / locality"
        />
      </FormField>

      <div className="grid grid-cols-2 gap-4">
        <FormField label="State" error={errors.state} required>
          <Select
            value={values.state}
            onChange={(e) => onChange("state", e.target.value)}
            placeholder="Select state"
            options={INDIAN_STATES.map((s) => ({ value: s, label: s }))}
          />
        </FormField>

        <FormField label="PIN code" error={errors.pinCode} required>
          <Input
            inputMode="numeric"
            maxLength={6}
            value={values.pinCode}
            onChange={(e) => onChange("pinCode", e.target.value.replace(/\D/g, ""))}
            placeholder="400001"
          />
        </FormField>
      </div>

      <FormField label="ABHA ID (optional)" hint="Your 14-digit Ayushman Bharat Health Account ID">
        <Input
          inputMode="numeric"
          value={values.abhaId}
          onChange={(e) => onChange("abhaId", e.target.value.replace(/\D/g, ""))}
          placeholder="14-2345-6789-0123"
        />
      </FormField>
    </div>
  );
}
