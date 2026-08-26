import { request } from "../client";
import type { components } from "../../types";

export type CopilotBrief = components["schemas"]["CopilotBrief"];
export type Citation = components["schemas"]["Citation"];

export function buildBrief(visitId: string): Promise<CopilotBrief> {
  return request<CopilotBrief>("/api/v1/copilot/brief", {
    method: "POST",
    body: JSON.stringify({ visit_id: visitId }),
  });
}
