import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { request } from "../client";
import { ApiError } from "../errors";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../env";

function envelope(code: string, message: string, requestId = "req-1") {
  return { error: { code, message, request_id: requestId, details: {} } };
}

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.getState().clear();
  useAuthStore.setState({ status: "idle" });
});

describe("api client", () => {
  it("parses the backend error envelope into a typed ApiError", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/whoami`, () =>
        HttpResponse.json(envelope("NOT_FOUND", "not found"), { status: 404 }),
      ),
    );

    await expect(request("/api/v1/whoami")).rejects.toMatchObject({
      code: "NOT_FOUND",
      status: 404,
      requestId: "req-1",
    });
  });

  it("treats a non-JSON error body as INTERNAL rather than throwing unhandled", async () => {
    server.use(http.get(`${env.apiBase}/api/v1/broken`, () => new HttpResponse("<html>oops</html>", { status: 500 })));

    let error: unknown;
    try {
      await request("/api/v1/broken", { _noRetry: true } as never);
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("INTERNAL");
  });

  it("always sends X-Request-ID and Accept-Language headers", async () => {
    let seenHeaders: Headers | null = null;
    server.use(
      http.get(`${env.apiBase}/api/v1/echo`, ({ request: req }) => {
        seenHeaders = req.headers;
        return HttpResponse.json({ ok: true });
      }),
    );

    await request("/api/v1/echo");
    const headers = seenHeaders as Headers | null;
    expect(headers?.get("X-Request-ID")).toBeTruthy();
    expect(headers?.get("Accept-Language")).toBeTruthy();
  });

  it("refreshes an expired access token once and replays the original request", async () => {
    useAuthStore.setState({ accessToken: "stale", status: "authenticated" });
    let calls = 0;
    server.use(
      http.get(`${env.apiBase}/api/v1/secret`, ({ request: req }) => {
        calls += 1;
        if (req.headers.get("Authorization") === "Bearer stale") {
          return HttpResponse.json(envelope("AUTH_TOKEN_EXPIRED", "expired"), { status: 401 });
        }
        return HttpResponse.json({ secret: true });
      }),
      http.post(`${env.apiBase}/api/v1/auth/refresh`, () => HttpResponse.json({ access_token: "fresh" })),
    );

    useAuthStore.setState({
      user: { id: "u1", email: "a@b.com", role: "patient", name: null },
    });

    const result = await request<{ secret: boolean }>("/api/v1/secret");
    expect(result.secret).toBe(true);
    expect(calls).toBe(2);
    expect(useAuthStore.getState().accessToken).toBe("fresh");
  });

  it("never persists the access token to localStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    useAuthStore.getState().setSession({ id: "u1", email: "a@b.com", role: "patient", name: null }, "tok");
    expect(spy).not.toHaveBeenCalledWith(expect.stringContaining("token"), expect.anything());
    spy.mockRestore();
  });
});
