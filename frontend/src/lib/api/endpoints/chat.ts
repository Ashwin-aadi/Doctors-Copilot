import { streamSse } from "../../sse";
import type { Citation } from "../../../components/types";

/**
 * `POST /api/v1/chat/patient` is a Server-Sent Event stream, not a JSON
 * response, so it does not go through `request()`. Wire contract, from
 * `backend/app/rag/patient_chat.py::chat_stream`:
 *
 *   event: token    data: {"text": "..."}      repeated
 *   event: citation data: Citation             once per source, after the text
 *   event: done     data: {"confidence": 0.0-1.0}
 *   event: error    data: {"code": "...", "message": "..."}
 *
 * Two conditions arrive inside the text rather than as their own frames: the
 * guardrail layer prefixes an emergency answer with `[[EMERGENCY]]`, and a
 * question outside the bot's scope comes back containing `SCOPE_REFUSAL`.
 * `useChatStream` strips both markers and raises them to the UI.
 */
export const EMERGENCY_MARKER = "[[EMERGENCY]]";
export const SCOPE_REFUSAL_MARKER = "SCOPE_REFUSAL";

export interface ChatHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatStreamHandlers {
  onToken: (text: string) => void;
  onCitation: (citation: Citation) => void;
  onDone: (confidence: number) => void;
  onError: (code: string, message: string) => void;
}

interface TokenData {
  text?: unknown;
}

interface DoneData {
  confidence?: unknown;
}

interface ErrorData {
  code?: unknown;
  message?: unknown;
}

export function streamPatientChat(
  params: { message: string; patientId?: string; history: ChatHistoryTurn[] },
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse("/api/v1/chat/patient", {
    signal,
    body: {
      message: params.message,
      patient_id: params.patientId,
      history: params.history,
    },
    onFrame: (frame) => {
      switch (frame.event) {
        case "token": {
          const text = (frame.data as TokenData)?.text;
          if (typeof text === "string") handlers.onToken(text);
          break;
        }
        case "citation":
          handlers.onCitation(frame.data as Citation);
          break;
        case "done": {
          const confidence = (frame.data as DoneData)?.confidence;
          handlers.onDone(typeof confidence === "number" ? confidence : 0);
          break;
        }
        case "error": {
          const data = frame.data as ErrorData;
          handlers.onError(
            typeof data?.code === "string" ? data.code : "INTERNAL",
            typeof data?.message === "string" ? data.message : "chat unavailable",
          );
          break;
        }
        default:
          break;
      }
    },
  });
}
