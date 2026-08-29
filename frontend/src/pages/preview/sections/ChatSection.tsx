import { useState } from "react";
import { Card } from "../../../components/ui/Card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { Skeleton } from "../../../components/ui/Skeleton";
import { MessageList } from "../../../components/chat/MessageList";
import { Composer } from "../../../components/chat/Composer";
import { QuickReplyChips } from "../../../components/chat/QuickReplyChips";
import { ScopeRefusalNotice } from "../../../components/chat/ScopeRefusalNotice";
import { TriageResultCard } from "../../../components/chat/TriageResultCard";
import { mockTriageResult } from "../../../mocks/mockTriageResult";
import type { ChatMessage } from "../../../components/types";
import type { PreviewState } from "../PreviewPage";

const seedMessages: ChatMessage[] = [
  { id: "m1", role: "system", content: "Chat started · 26 Aug 2026", createdAt: "2026-08-26T09:00:00Z" },
  { id: "m2", role: "assistant", content: "Hello, I'm here to understand what's bothering you today. What symptoms are you having?", createdAt: "2026-08-26T09:00:05Z" },
  { id: "m3", role: "patient", content: "I've had high fever for 4 days and my gums have started bleeding.", createdAt: "2026-08-26T09:00:40Z" },
  {
    id: "m4",
    role: "emergency",
    content: "Bleeding gums with prolonged fever can be a dengue warning sign [1]. I'm flagging this for urgent review.",
    citations: mockTriageResult.citations,
    createdAt: "2026-08-26T09:01:10Z",
  },
];

export function ChatSection({ state }: { state: PreviewState }) {
  const [messages, setMessages] = useState(seedMessages);
  const [draft, setDraft] = useState("");

  function handleSend() {
    if (!draft.trim()) return;
    setMessages((prev) => [
      ...prev,
      { id: `m${prev.length + 1}`, role: "patient", content: draft, createdAt: new Date().toISOString() },
    ]);
    setDraft("");
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="flex h-[26rem] flex-col overflow-hidden p-0">
        {state === "loading" && (
          <div className="flex flex-1 flex-col gap-3 p-4">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="ml-auto h-10 w-1/2" />
            <Skeleton className="h-10 w-3/4" />
          </div>
        )}
        {state === "empty" && (
          <div className="flex flex-1 items-center justify-center p-4">
            <EmptyState title="No conversation yet" description="Start by describing your symptoms below." />
          </div>
        )}
        {state === "error" && (
          <div className="flex flex-1 items-center justify-center p-4">
            <ErrorState title="Couldn't reach the triage assistant" description="Check your connection and try again." />
          </div>
        )}
        {state === "success" && (
          <>
            <div className="flex-1 overflow-hidden">
              <MessageList messages={messages} />
            </div>
            <div className="border-t border-border p-3">
              <QuickReplyChips
                replies={["It's getting worse", "No other symptoms", "I also feel dizzy"]}
                onSelect={(r) => setDraft(r)}
              />
            </div>
            <Composer value={draft} onChange={setDraft} onSend={handleSend} />
            <div className="p-3 pt-0">
              <ScopeRefusalNotice />
            </div>
          </>
        )}
      </Card>

      <div className="h-[26rem] overflow-y-auto">
        <TriageResultCard result={mockTriageResult} onCitationClick={() => {}} />
      </div>
    </div>
  );
}
