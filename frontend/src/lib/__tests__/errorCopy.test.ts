import { describe, expect, it } from "vitest";
import { getErrorCopy } from "../errorCopy";
import type { ErrorCode } from "../api/errors";

const ALL_CODES: ErrorCode[] = [
  "AUTH_INVALID_CREDENTIALS",
  "AUTH_TOKEN_EXPIRED",
  "AUTH_FORBIDDEN",
  "CAPTCHA_REQUIRED",
  "CAPTCHA_INVALID",
  "VALIDATION_FAILED",
  "NOT_FOUND",
  "LOCKED",
  "CONFLICT",
  "RATE_LIMITED",
  "UPSTREAM_UNAVAILABLE",
  "MODEL_UNAVAILABLE",
  "INTERNAL",
  "NOT_IMPLEMENTED",
];

describe("errorCopy", () => {
  it("maps every backend error code to plain-language copy in both locales", () => {
    for (const code of ALL_CODES) {
      for (const lang of ["en", "hi"] as const) {
        const entry = getErrorCopy(code, lang);
        expect(entry.title.length).toBeGreaterThan(0);
        expect(entry.description.length).toBeGreaterThan(0);
        // The raw SCREAMING_SNAKE_CASE code must never leak into user copy
        // (plain English words like "locked" overlapping a code are fine).
        expect(entry.title).not.toMatch(/[A-Z]+_[A-Z]+/);
        expect(entry.description).not.toMatch(/[A-Z]+_[A-Z]+/);
      }
    }
  });

  it("reassures the user their work is saved for flaky-connection codes", () => {
    expect(getErrorCopy("UPSTREAM_UNAVAILABLE").description).toMatch(/saved/i);
    expect(getErrorCopy("MODEL_UNAVAILABLE").description).toMatch(/saved/i);
  });
});
