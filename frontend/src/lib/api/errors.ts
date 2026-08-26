export type ErrorCode =
  | "AUTH_INVALID_CREDENTIALS"
  | "AUTH_TOKEN_EXPIRED"
  | "AUTH_FORBIDDEN"
  | "CAPTCHA_REQUIRED"
  | "CAPTCHA_INVALID"
  | "VALIDATION_FAILED"
  | "NOT_FOUND"
  | "LOCKED"
  | "CONFLICT"
  | "RATE_LIMITED"
  | "UPSTREAM_UNAVAILABLE"
  | "MODEL_UNAVAILABLE"
  | "INTERNAL"
  | "NOT_IMPLEMENTED";

export class ApiError extends Error {
  code: ErrorCode;
  requestId?: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(
    code: ErrorCode,
    message: string,
    status: number,
    requestId?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

interface ErrorEnvelope {
  error: {
    code: ErrorCode;
    message: string;
    request_id: string;
    details?: Record<string, unknown>;
  };
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const err = (value as { error?: unknown }).error;
  return typeof err === "object" && err !== null && "code" in err && "message" in err;
}

export async function parseApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (isErrorEnvelope(body)) {
    return new ApiError(
      body.error.code,
      body.error.message,
      response.status,
      body.error.request_id,
      body.error.details,
    );
  }

  return new ApiError("INTERNAL", "internal server error", response.status);
}
