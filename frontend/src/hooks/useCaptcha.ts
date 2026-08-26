import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCaptchaChallenge } from "../lib/api/captcha";
import { qk } from "../lib/queryKeys";
import type { CaptchaChallenge } from "../components/forms/CaptchaWidget";

export interface UseCaptchaResult {
  challenge: CaptchaChallenge | null;
  token: string | null;
  onToken: (token: string) => void;
  onRefresh: () => void;
  reset: () => void;
}

export function useCaptcha(): UseCaptchaResult {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: qk.captcha(),
    queryFn: fetchCaptchaChallenge,
    staleTime: 0,
    gcTime: 0,
  });

  const onRefresh = useCallback(() => {
    setToken(null);
    void queryClient.invalidateQueries({ queryKey: qk.captcha() });
  }, [queryClient]);

  const reset = onRefresh;

  return { challenge: data ?? null, token, onToken: setToken, onRefresh, reset };
}
