import { FormField } from "../../../components/forms/FormField";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import type { StepProps } from "../types";

export function IdentityStep({ values, errors, onChange }: StepProps) {
  return (
    <div className="flex flex-col gap-4">
      <FormField label="Full name" error={errors.name} required>
        <Input
          value={values.name}
          onChange={(e) => onChange("name", e.target.value)}
          onBlur={(e) => onChange("name", e.target.value.trim())}
          placeholder="As on your ABHA card or ID"
        />
      </FormField>

      <FormField label="Date of birth" error={errors.dob} required>
        <Input type="date" value={values.dob} onChange={(e) => onChange("dob", e.target.value)} />
      </FormField>

      <FormField label="Sex" error={errors.sex} required>
        <Select
          value={values.sex}
          onChange={(e) => onChange("sex", e.target.value)}
          placeholder="Select"
          options={[
            { value: "female", label: "Female" },
            { value: "male", label: "Male" },
            { value: "other", label: "Other" },
          ]}
        />
      </FormField>
    </div>
  );
}
