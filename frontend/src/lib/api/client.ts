import { env } from "../env";
import { useAuthStore } from "../../store/auth";
import { ApiError, parseApiError } from "./errors";

export interface RequestOptions extends RequestInit {
  captchaToken?: string;
  /** Internal: set on the retry after a token refresh, to avoid refresh loops. */
  _isRetry?: boolean;
  /** Internal: skip the 5xx/network retry (used for the refresh call itself). */
  _noRetry?: boolean;
}

let refreshPromise: Promise<void> | null = null;

async function refreshAccessToken(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const res = await fetch(`${env.apiBase}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        useAuthStore.getState().clear();
        throw await parseApiError(res);
      }
      const body = (await res.json()) as { access_token: string };
      const current = useAuthStore.getState().user;
      if (current) {
        useAuthStore.getState().setSession(current, body.access_token);
      }
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jitter(base: number): number {
  return base + Math.random() * base * 0.3;
}

export async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { captchaToken, _isRetry, _noRetry, ...rest } = init;
  const accessToken = useAuthStore.getState().accessToken;
  const locale = document.documentElement.lang || "en";

  const headers = new Headers(rest.headers);
  headers.set("Accept", "application/json");
  headers.set("Accept-Language", locale);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (rest.body && !headers.has("Content-Type") && typeof rest.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (captchaToken) headers.set("X-Captcha-Token", captchaToken);

  let response: Response;
  try {
    response = await fetch(`${env.apiBase}${path}`, {
      ...rest,
      headers,
      credentials: "include",
    });
  } catch {
    if (!_noRetry && (rest.method ?? "GET") === "GET") {
      return retryOnNetworkError<T>(path, init);
    }
    throw new ApiError("UPSTREAM_UNAVAILABLE", "network request failed", 0);
  }

  if (response.status === 401 && !_isRetry) {
    const error = await parseApiError(response.clone());
    if (error.code === "AUTH_TOKEN_EXPIRED") {
      try {
        await refreshAccessToken();
        return request<T>(path, { ...init, _isRetry: true });
      } catch {
        throw error;
      }
    }
    throw error;
  }

  if (response.status === 429 && !_noRetry) {
    return retryOnRateLimit<T>(path, init, response, 0);
  }

  if (response.status >= 500 && !_noRetry && (rest.method ?? "GET") === "GET") {
    return retryOnServerError<T>(path, init, 0);
  }

  if (!response.ok) {
    throw await parseApiError(response);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

async function retryOnNetworkError<T>(path: string, init: RequestOptions, attempt = 0): Promise<T> {
  if (attempt >= 2) throw new ApiError("UPSTREAM_UNAVAILABLE", "network request failed", 0);
  await sleep(jitter(300 * 2 ** attempt));
  try {
    return await request<T>(path, { ...init, _noRetry: true });
  } catch {
    return retryOnNetworkError<T>(path, init, attempt + 1);
  }
}

async function retryOnServerError<T>(path: string, init: RequestOptions, attempt: number): Promise<T> {
  if (attempt >= 2) {
    const res = await fetch(`${env.apiBase}${path}`, { ...init, credentials: "include" });
    throw await parseApiError(res);
  }
  await sleep(jitter(300 * 2 ** attempt));
  try {
    return await request<T>(path, { ...init, _noRetry: true });
  } catch (err) {
    if (err instanceof ApiError && err.status >= 500) {
      return retryOnServerError<T>(path, init, attempt + 1);
    }
    throw err;
  }
}

async function retryOnRateLimit<T>(
  path: string,
  init: RequestOptions,
  response: Response,
  attempt: number,
): Promise<T> {
  if (attempt >= 3) throw await parseApiError(response);
  const retryAfter = Number(response.headers.get("Retry-After")) || 2 ** attempt;
  await sleep(retryAfter * 1000);
  return request<T>(path, { ...init, _noRetry: true });
}
