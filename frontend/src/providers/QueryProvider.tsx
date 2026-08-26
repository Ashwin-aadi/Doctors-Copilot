import { useState, type ReactNode } from "react";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ApiError } from "../lib/api/errors";
import { useToast } from "../components/ui/Toast";

function createQueryClient(onError: (error: unknown) => void): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        onError,
      },
    },
    queryCache: new QueryCache({ onError }),
  });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const { push } = useToast();
  const { t } = useTranslation();

  const [client] = useState(() =>
    createQueryClient((error: unknown) => {
      if (error instanceof ApiError) {
        push({
          tone: "error",
          title: t(`errorCodes.${error.code}`, { defaultValue: error.message }),
          description: error.requestId ? t("errors.requestId", { id: error.requestId }) : undefined,
        });
      }
    }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
