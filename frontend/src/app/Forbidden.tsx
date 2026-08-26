import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ShieldOff } from "lucide-react";
import { ErrorState } from "../components/ui/ErrorState";
import { Button } from "../components/ui/Button";

export function Forbidden() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <ErrorState
        icon={<ShieldOff className="h-8 w-8" />}
        title={t("errors.forbiddenTitle")}
        description={t("errors.forbiddenBody")}
        action={
          <Button variant="secondary" onClick={() => navigate("/")}>
            {t("errors.goHome")}
          </Button>
        }
      />
    </div>
  );
}
