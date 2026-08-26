import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  getTriageResult,
  sendTriageMessage,
  startTriageSession,
  type TriageResult,
} from "../../lib/api/endpoints/triage";
import { useSessionStore } from "../../store/session";
import { useAuthStore } from "../../store/auth";
import { qk } from "../../lib/queryKeys";
import type { ChatMessage } from "../../components/types";

const TRANSCRIPT_KEY = "docopilot_triage_transcript";

function loadTranscript(sessionId: string): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(`${TRANSCRIPT_KEY}:${sessionId}`);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

function saveTranscript(sessionId: string, messages: ChatMessage[]): void {
  try {
    sessionStorage.setItem(`${TRANSCRIPT_KEY}:${sessionId}`, JSON.stringify(messages));
  } catch {
    // best-effort only
  }
}

let bubbleCounter = 0;
function nextId(): string {
  bubbleCounter += 1;
  return `bubble-${Date.now()}-${bubbleCounter}`;
}

export function useTriageSession() {
  const patientId = useAuthStore((s) => s.user?.patientId);
  const sessionId = useSessionStore((s) => s.triageSessionId);
  const setSessionId = useSessionStore((s) => s.setTriageSessionId);

  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    sessionId ? loadTranscript(sessionId) : [],
  );
  const [done, setDone] = useState(false);
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const startedRef = useRef(false);

  const startMutation = useMutation({
    mutationFn: () => startTriageSession(patientId),
    onSuccess: (turn) => {
      setSessionId(turn.session_id);
      const restored = loadTranscript(turn.session_id);
      const next =
        restored.length > 0
          ? restored
          : [
              {
                id: nextId(),
                role: "assistant" as const,
                content: turn.assistant,
                quickReplies: turn.quick_replies,
                createdAt: new Date().toISOString(),
              },
            ];
      setMessages(next);
      setQuickReplies(turn.quick_replies);
      setDone(turn.done);
      saveTranscript(turn.session_id, next);
    },
  });

  const sendMutation = useMutation({
    mutationFn: (content: string) => {
      if (!sessionId) throw new Error("no active triage session");
      return sendTriageMessage(sessionId, content);
    },
    onSuccess: (turn) => {
      setMessages((prev) => {
        const next: ChatMessage[] = [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content: turn.assistant,
            quickReplies: turn.quick_replies,
            createdAt: new Date().toISOString(),
          },
        ];
        if (sessionId) saveTranscript(sessionId, next);
        return next;
      });
      setQuickReplies(turn.quick_replies);
      setDone(turn.done);
    },
  });

  const resultQuery = useQuery<TriageResult>({
    queryKey: sessionId ? qk.triage(sessionId) : ["triage", "none"],
    queryFn: () => getTriageResult(sessionId as string),
    enabled: done && Boolean(sessionId),
  });

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    if (!sessionId) {
      startMutation.mutate();
    } else {
      setMessages(loadTranscript(sessionId));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function sendMessage(content: string) {
    if (!content.trim() || !sessionId) return;
    setMessages((prev) => {
      const next: ChatMessage[] = [
        ...prev,
        { id: nextId(), role: "patient", content, createdAt: new Date().toISOString() },
      ];
      saveTranscript(sessionId, next);
      return next;
    });
    sendMutation.mutate(content);
  }

  return {
    sessionId,
    messages,
    quickReplies,
    done,
    result: resultQuery.data,
    resultLoading: resultQuery.isLoading,
    sending: sendMutation.isPending,
    starting: startMutation.isPending,
    startError: startMutation.error,
    sendMessage,
  };
}
