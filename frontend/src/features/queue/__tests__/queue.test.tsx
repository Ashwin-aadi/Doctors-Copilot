import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { QueueBoardContainer } from "../QueueBoardContainer";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";
import type { QueueEntry } from "../../../lib/api/endpoints/queue";

vi.mock("../useQueueSocket", () => ({
  useQueueSocket: () => ({ status: "reconnecting" }),
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
    user: { id: "d1", email: "doc@clinic.in", role: "doctor", name: "Dr. Rao", clinicId: "clinic-1" },
  });
});

function renderContainer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <QueueBoardContainer />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function entry(overrides: Partial<QueueEntry> = {}): QueueEntry {
  return {
    id: "e1",
    patient_id: "p1",
    patient_name: "Asha Devi",
    doctor_id: "d1",
    clinic_id: "clinic-1",
    severity_esi: 3,
    triage_colour: "yellow",
    emergency: false,
    position: 1,
    waited_minutes: 12,
    estimated_wait_minutes: 8,
    status: "waiting",
    reasons: [],
    token: "A-12",
    reasons_hi: [],
    ...overrides,
  };
}

describe("QueueBoardContainer", () => {
  it("renders the waiting room with the seeded queue entries", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/queue/clinic-1`, () => HttpResponse.json([entry()])),
    );

    renderContainer();
    expect(await screen.findByText("Asha Devi")).toBeTruthy();
    expect(screen.getByText(/Reconnecting/i)).toBeTruthy();
  });

  it("shows the empty state when no one is waiting", async () => {
    server.use(http.get(`${env.apiBase}/api/v1/queue/clinic-1`, () => HttpResponse.json([])));

    renderContainer();
    expect(await screen.findByText(/No patients waiting/i)).toBeTruthy();
  });

  it("optimistically removes the head entry on call next and rolls back on failure", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/queue/clinic-1`, () => HttpResponse.json([entry()])),
      http.post(`${env.apiBase}/api/v1/queue/e1/next`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 80));
        return HttpResponse.json({ error: { code: "INTERNAL", message: "boom", request_id: "r1" } }, { status: 500 });
      }),
    );

    renderContainer();
    const callNext = await screen.findByRole("button", { name: /call next/i });
    fireEvent.click(callNext);

    await waitFor(() => expect(screen.queryByText("Asha Devi")).toBeNull());
    await waitFor(() => expect(screen.getByText("Asha Devi")).toBeTruthy(), { timeout: 3000 });
  });
});
