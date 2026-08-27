import { request } from "../client";
import type { components } from "../../types";
import type { BlockedSubstitutionSeverity, GenericOption } from "../../../components/types";

/**
 * Generated from the live contract -- never hand-typed. Every money field is
 * INR; render with `formatInr` and never a dollar sign.
 */
export type GenericProduct = components["schemas"]["GenericProduct"];
export type BlockedOption = components["schemas"]["BlockedOption"];
export type SubstitutionRow = components["schemas"]["Substitution"];
/**
 * `GET /medications/generic` carries no Pydantic `response_model`, so
 * openapi-typescript only sees a bare object -- hand-typed against
 * `backend/app/api/v1/medications.py`, same precedent as `endpoints/auth.ts`.
 * `schedule_h` is a single boolean that cannot distinguish Schedule H from H1
 * (one column in india_drugs.csv), so never drive an H1-only statutory warning
 * from it: the reliable H1 signal is a blocked option with severity
 * `schedule_h1`.
 */
export interface GenericMapping {
  input: string;
  rxcui: string | null;
  ingredient: string;
  generics: GenericProduct[];
  nlem: boolean;
  schedule_h: boolean;
  source_url: string | null;
  cached: boolean;
  reasons: string[];
}

/**
 * The wire types `severity` as a bare string. The real vocabulary is the
 * safety reason the substitute was rejected for -- `allergy`,
 * `contraindication`, `schedule_h1`, `not_equivalent`, `major` -- which
 * overlaps the interaction severities only at `major`. Anything unrecognised
 * falls back to `major`, the most cautious label.
 */
const BLOCKED_SEVERITIES: BlockedSubstitutionSeverity[] = [
  "allergy",
  "contraindication",
  "schedule_h1",
  "not_equivalent",
  "major",
  "moderate",
  "minor",
];

export function toBlockedSeverity(value: string): BlockedSubstitutionSeverity {
  return BLOCKED_SEVERITIES.includes(value as BlockedSubstitutionSeverity)
    ? (value as BlockedSubstitutionSeverity)
    : "major";
}

/** snake_case wire shape -> the camelCase `GenericOption` the UI layer speaks. */
export function toGenericOption(product: GenericProduct): GenericOption {
  return {
    name: product.name,
    rxcui: product.rxcui ?? null,
    form: product.form ?? null,
    strength: product.strength ?? null,
    janAushadhiCode: product.jan_aushadhi_code ?? null,
    mrpInr: product.mrp_inr ?? null,
    priceInr: product.price_inr ?? null,
    nppaCeilingInr: product.nppa_ceiling_inr ?? null,
    savingsPct: product.savings_pct ?? null,
  };
}

/**
 * Doctor/staff only -- a patient token gets `AUTH_FORBIDDEN`, so this must
 * never be called from a patient-facing surface. Exactly one of the two
 * identifiers is required; `visit_id` resolves to the visit's latest
 * prescription and 404s when it has none yet. Every row echoes back the
 * resolved `prescription_id`, which is the only way a visit surface can learn
 * the id it needs to lock and export the prescription: there is no GET or POST
 * prescription route, and `VisitOut` carries no prescription id.
 */
export function getSubstitutions(params: {
  prescriptionId?: string;
  visitId?: string;
}): Promise<SubstitutionRow[]> {
  const query = new URLSearchParams();
  if (params.prescriptionId) query.set("prescription_id", params.prescriptionId);
  if (params.visitId) query.set("visit_id", params.visitId);
  return request<SubstitutionRow[]>(`/api/v1/medications/substitutions?${query.toString()}`);
}

export function getGeneric(name: string): Promise<GenericMapping> {
  return request<GenericMapping>(`/api/v1/medications/generic?name=${encodeURIComponent(name)}`);
}
