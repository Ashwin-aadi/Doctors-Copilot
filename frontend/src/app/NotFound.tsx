import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { SearchX } from "lucide-react";
import { ErrorState } from "../components/ui/ErrorState";
import { Button } from "../components/ui/Button";

export function NotFound() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <ErrorState
        icon={<SearchX className="h-8 w-8" />}
        title={t("errors.notFoundTitle")}
        description={t("errors.notFoundBody")}
        action={
          <Button variant="secondary" onClick={() => navigate("/")}>
            {t("errors.goHome")}
          </Button>
        }
      />
    </div>
  );
}
