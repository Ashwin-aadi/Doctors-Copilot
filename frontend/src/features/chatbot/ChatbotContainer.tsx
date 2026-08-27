import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessageList } from "../../components/chat/MessageList";
import { ScopeRefusalNotice } from "../../components/chat/ScopeRefusalNotice";
import { EmergencyBanner } from "../../components/alerts/EmergencyBanner";
import { Composer } from "../../components/chat/Composer";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { ErrorState } from "../../components/ui/ErrorState";
import { ROUTES } from "../../router/routes";
import { useChatStream } from "./useChatStream";

export function ChatbotContainer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [draft, setDraft] = useState("");
  const { messages, streaming, emergency, error, send } = useChatStream();

  const refusal = messages.find((m) => m.scopeRefusal && m.content.length > 0);
  const visible = messages.filter((m) => !m.scopeRefusal);

  function handleSend() {
    send(draft);
    setDraft("");
  }

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {emergency && (
        <div data-testid="emergency-banner">
          <EmergencyBanner
            message={t("chat.emergencyBanner")}
            onFindClinic={() => navigate(`${ROUTES.booking}?emergency=1`)}
          />
        </div>
      )}

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardHeader>
          <CardTitle>{t("chat.title")}</CardTitle>
        </CardHeader>
        <CardBody className="flex min-h-0 flex-1 flex-col gap-3">
          <p className="text-xs text-fg-muted">{t("chat.scopeNote")}</p>
          <MessageList messages={visible} typing={streaming} />
          {refusal && <ScopeRefusalNotice />}
          {error && <ErrorState title={t("chat.streamError")} description={error} />}
          <Composer
            value={draft}
            onChange={setDraft}
            onSend={handleSend}
            sending={streaming}
            placeholder={t("chat.placeholder")}
          />
        </CardBody>
      </Card>
    </div>
  );
}
