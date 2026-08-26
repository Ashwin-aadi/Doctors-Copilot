import { request } from "./client";
import type { CaptchaChallenge } from "../../components/forms/CaptchaWidget";

export function fetchCaptchaChallenge(): Promise<CaptchaChallenge> {
  return request<CaptchaChallenge>("/api/v1/captcha/challenge");
}

async function solveCaptcha(challenge: CaptchaChallenge): Promise<string> {
  const enc = new TextEncoder();
  for (let n = 0; n <= challenge.maxnumber; n++) {
    const digest = await crypto.subtle.digest("SHA-256", enc.encode(challenge.salt + String(n)));
    const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
    if (hex === challenge.challenge) {
      return btoa(JSON.stringify({ challenge: challenge.challenge, salt: challenge.salt, number: n }));
    }
  }
  throw new Error("captcha_unsolvable");
}

/**
 * For protected mutations with no visible CaptchaWidget in the flow (e.g.
 * background upload retries). Screens that render CaptchaWidget should use
 * useCaptcha() instead, since the widget solves and displays progress itself.
 */
export async function withCaptcha<T>(fn: (token: string) => Promise<T>): Promise<T> {
  const challenge = await fetchCaptchaChallenge();
  const token = await solveCaptcha(challenge);
  try {
    return await fn(token);
  } catch (err) {
    const isInvalid = err instanceof Error && err.message.includes("CAPTCHA_INVALID");
    if (!isInvalid) throw err;
    const retryChallenge = await fetchCaptchaChallenge();
    const retryToken = await solveCaptcha(retryChallenge);
    return fn(retryToken);
  }
}
