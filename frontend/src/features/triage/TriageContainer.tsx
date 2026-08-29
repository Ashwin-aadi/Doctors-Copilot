import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card } from "../../components/ui/Card";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { Button } from "../../components/ui/Button";
import { MessageList } from "../../components/chat/MessageList";
import { Composer } from "../../components/chat/Composer";
import { QuickReplyChips } from "../../components/chat/QuickReplyChips";
import { TriageResultCard } from "../../components/chat/TriageResultCard";
import { useTriageSession } from "./useTriageSession";
import { ROUTES } from "../../router/routes";

export function TriageContainer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [draft, setDraft] = useState("");
  const {
    messages,
    quickReplies,
    done,
    result,
    resultLoading,
    sending,
    starting,
    startError,
    sendMessage,
  } = useTriageSession();

  function handleSend() {
    if (!draft.trim()) return;
    sendMessage(draft);
    setDraft("");
  }

  if (starting && messages.length === 0) {
    return (
      <div className="mx-auto flex h-[80vh] max-w-2xl flex-col gap-3 p-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="ml-auto h-10 w-1/2" />
        <Skeleton className="h-10 w-3/4" />
      </div>
    );
  }

  if (startError) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <ErrorState
          title={t("errorCodes.UPSTREAM_UNAVAILABLE")}
          description={startError instanceof Error ? startError.message : undefined}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-4xl gap-4 p-4 md:grid-cols-2">
      <Card className="flex h-[80vh] flex-col p-0">
        <div className="flex-1 overflow-hidden">
          <MessageList messages={messages} typing={sending} />
        </div>
        {!done && quickReplies.length > 0 && (
          <div className="border-t border-border p-3">
            <QuickReplyChips replies={quickReplies} onSelect={(r) => sendMessage(r)} disabled={sending} />
          </div>
        )}
        {!done && <Composer value={draft} onChange={setDraft} onSend={handleSend} sending={sending} />}
      </Card>

      <div className="h-[80vh] overflow-y-auto">
        {done && resultLoading && (
          <div className="flex flex-col gap-3 p-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        )}
        {done && result && (
          <div className="flex flex-col gap-3">
            <TriageResultCard result={result} onCitationClick={() => {}} />
            <Button
              onClick={() =>
                navigate(ROUTES.booking, {
                  // The session id has to travel with the booking: it is what
                  // ties the visit the doctor opens to this interview rather
                  // than to whatever triage ran on this patient before.
                  state: {
                    specialty: result.specialty,
                    severityEsi: result.severity_esi,
                    triageSessionId: result.session_id,
                  },
                })
              }
            >
              Find a doctor for {result.specialty}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
