import type { CopilotBrief } from "../components/types";

export const mockCopilotBrief: CopilotBrief = {
  visit_id: "00000000-0000-0000-0000-000000000301",
  summary:
    "42-year-old woman with poorly controlled type 2 diabetes presents with fatigue and blurred vision; HbA1c 8.2% and fasting glucose 168 mg/dL support suboptimal glycaemic control [1]. No acute infective signs.",
  differentials: ["Uncontrolled type 2 diabetes mellitus", "Diabetic retinopathy (early)", "Anaemia of chronic disease"],
  recommended_procedures: ["Dilated fundus examination", "Lipid profile", "Urine microalbumin"],
  cautions: ["Metformin dose adjustment needed if renal function declines", "Screen for peripheral neuropathy"],
  citations: [
    { n: 1, title: "ICMR Guidelines for Management of Type 2 Diabetes", source: "ICMR", url: "https://www.icmr.gov.in", snippet: "HbA1c above 8% indicates need for treatment intensification.", published: "2018" },
  ],
  confidence: 0.78,
};
