import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NotificationsContainer } from "../NotificationsContainer";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";

vi.mock("../useNotificationSocket", () => ({
  useNotificationSocket: () => ({ status: "reconnecting" }),
}));

const server = setupServer();

beforeAll(async () => {
  await initI18n();
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.getState().clear();
  useAuthStore.setState({
    accessToken: "tok",
    status: "authenticated",
    user: { id: "d1", email: "doc@clinic.in", role: "doctor", name: "Dr. Rao" },
  });
});

function renderBell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NotificationsContainer />
    </QueryClientProvider>,
  );
}

describe("NotificationsContainer", () => {
  it("shows the not-ready notice when the backend 501s", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/notify`, () =>
        HttpResponse.json(
          { error: { code: "NOT_IMPLEMENTED", message: "notifications owned by pratyaksh", request_id: "r1" } },
          { status: 501 },
        ),
      ),
    );

    renderBell();
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    // client.ts retries a GET on any 5xx (501 included) twice with backoff
    // before surfacing the error, so this needs more than the default 1s.
    expect(await screen.findByText(/isn't ready yet/i, {}, { timeout: 5000 })).toBeTruthy();
  });

  it("shows an unread count and marks a notification read optimistically", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/notify`, () =>
        HttpResponse.json([
          { id: "n1", title: "Lab results ready", body: "CBC results are in", read: false, created_at: "2026-08-27T09:00:00Z" },
        ]),
      ),
      http.post(`${env.apiBase}/api/v1/notify/n1/read`, () =>
        HttpResponse.json({ id: "n1", title: "Lab results ready", body: "CBC results are in", read: true, created_at: "2026-08-27T09:00:00Z" }),
      ),
    );

    renderBell();
    expect(await screen.findByText("1")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    const item = await screen.findByText("Lab results ready");
    fireEvent.click(item);

    await waitFor(() => expect(screen.queryByText("1")).toBeNull());
  });
});
