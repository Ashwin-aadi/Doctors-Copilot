import { useCallback, useEffect, useRef, useState } from "react";
import {
  EMERGENCY_MARKER,
  SCOPE_REFUSAL_MARKER,
  streamPatientChat,
  type ChatHistoryTurn,
} from "../../lib/api/endpoints/chat";
import { ApiError } from "../../lib/api/errors";
import { useAuthStore } from "../../store/auth";
import type { ChatMessage, Citation } from "../../components/types";

let bubbleCounter = 0;
function nextId(): string {
  bubbleCounter += 1;
  return `chat-${Date.now()}-${bubbleCounter}`;
}

/** Markers travel inside the answer text; strip them before anything renders. */
function classify(text: string): {
  content: string;
  emergency: boolean;
  scopeRefusal: boolean;
} {
  const emergency = text.includes(EMERGENCY_MARKER);
  const scopeRefusal = text.includes(SCOPE_REFUSAL_MARKER);
  const content = text
    .split(EMERGENCY_MARKER)
    .join("")
    .split(SCOPE_REFUSAL_MARKER)
    .join("")
    .trim();
  return { content, emergency, scopeRefusal };
}

export interface ChatStreamState {
  messages: ChatMessage[];
  streaming: boolean;
  emergency: boolean;
  error: string | null;
  send: (message: string) => void;
  dismissEmergency: () => void;
}

export function useChatStream(): ChatStreamState {
  const patientId = useAuthStore((s) => s.user?.patientId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [emergency, setEmergency] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const historyRef = useRef<ChatHistoryTurn[]>([]);

  // Abort any in-flight stream when the container unmounts, so a patient who
  // navigates away mid-answer does not keep a socket open on mobile data.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const send = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;

      // A new question supersedes the previous answer: abort it rather than
      // interleaving two token streams into one bubble.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setError(null);
      setEmergency(false);
      setStreaming(true);

      const assistantId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "patient", content: trimmed, createdAt: new Date().toISOString() },
        { id: assistantId, role: "assistant", content: "", createdAt: new Date().toISOString() },
      ]);

      let buffered = "";
      const citations: Citation[] = [];

      const patch = (updater: (msg: ChatMessage) => ChatMessage) =>
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? updater(m) : m)));

      void streamPatientChat(
        { message: trimmed, patientId, history: historyRef.current },
        {
          onToken: (text) => {
            buffered += text;
            const { content, emergency: isEmergency, scopeRefusal } = classify(buffered);
            if (isEmergency) setEmergency(true);
            patch((m) => ({
              ...m,
              content,
              role: isEmergency ? "emergency" : "assistant",
              scopeRefusal,
            }));
          },
          onCitation: (citation) => {
            citations.push(citation);
            patch((m) => ({ ...m, citations: [...citations] }));
          },
          onDone: () => {
            historyRef.current = [
              ...historyRef.current,
              { role: "user", content: trimmed },
              { role: "assistant", content: classify(buffered).content },
            ];
            setStreaming(false);
          },
          onError: (_code, message) => {
            setError(message);
            setStreaming(false);
          },
        },
        controller.signal,
      ).catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiError ? err.code : "INTERNAL");
        setStreaming(false);
      });
    },
    [patientId],
  );

  const dismissEmergency = useCallback(() => setEmergency(false), []);

  return { messages, streaming, emergency, error, send, dismissEmergency };
}
