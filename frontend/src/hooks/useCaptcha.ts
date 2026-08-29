import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCaptchaChallenge } from "../lib/api/captcha";
import { qk } from "../lib/queryKeys";
import type { CaptchaChallenge } from "../components/forms/CaptchaWidget";

export interface UseCaptchaResult {
  /** False when the server is not enforcing the captcha; screens skip the
   * verification step entirely rather than showing a no-op widget. */
  enabled: boolean;
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

  return {
    enabled: data?.enabled !== false,
    challenge: data ?? null,
    token,
    onToken: setToken,
    onRefresh,
    reset,
  };
}
