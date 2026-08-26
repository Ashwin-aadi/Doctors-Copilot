import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { LabOrderApprovalContainer } from "../LabOrderApprovalContainer";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function validCaptchaChallenge() {
  const salt = "test-salt";
  const number = 3;
  const challenge = await sha256Hex(salt + String(number));
  return { challenge, salt, maxnumber: 50 };
}

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

function renderContainer(labOrderId = "lo1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/doctor/lab-order/${labOrderId}`]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/doctor/lab-order/:id" element={<LabOrderApprovalContainer />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("LabOrderApprovalContainer", () => {
  it("approves a draft lab order with captcha and shows the locked state", async () => {
    let locked = false;
    server.use(
      http.get(`${env.apiBase}/api/v1/lab-orders/lo1`, () =>
        HttpResponse.json({
          id: "lo1",
          visit_id: "v1",
          patient_id: "p1",
          status: locked ? "approved" : "draft",
          locked,
          items: [{ name: "CBC", reason: "fever workup", source: "rule" }],
          approved_by: locked ? "d1" : null,
          approved_at: locked ? "2026-08-27T10:00:00Z" : null,
        }),
      ),
      http.get(`${env.apiBase}/api/v1/captcha/challenge`, async () =>
        HttpResponse.json(await validCaptchaChallenge()),
      ),
      http.post(`${env.apiBase}/api/v1/approvals/lab-order/lo1`, () => {
        locked = true;
        return HttpResponse.json({
          id: "lo1",
          status: "approved",
          locked: true,
          approved_by: "d1",
          approved_at: "2026-08-27T10:00:00Z",
          content_hash: "hash1",
        });
      }),
    );

    renderContainer();
    expect(await screen.findByText("CBC")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /approve lab order/i }));
    await waitFor(() => expect(screen.getByText(/verification complete/i)).toBeTruthy(), { timeout: 5000 });

    fireEvent.click(screen.getByRole("button", { name: /confirm approval/i }));

    expect(await screen.findByText(/approved and locked/i)).toBeTruthy();
  });

  it("shows the locked state instead of an error toast on a 409 LOCKED race", async () => {
    let approveCallCount = 0;
    server.use(
      http.get(`${env.apiBase}/api/v1/lab-orders/lo2`, () => {
        approveCallCount += 1;
        const locked = approveCallCount > 1;
        return HttpResponse.json({
          id: "lo2",
          visit_id: "v1",
          patient_id: "p1",
          status: locked ? "approved" : "draft",
          locked,
          items: [{ name: "LFT", reason: "jaundice", source: "rule" }],
          approved_by: locked ? "someone-else" : null,
          approved_at: locked ? "2026-08-27T09:00:00Z" : null,
        });
      }),
      http.get(`${env.apiBase}/api/v1/captcha/challenge`, async () =>
        HttpResponse.json(await validCaptchaChallenge()),
      ),
      http.post(`${env.apiBase}/api/v1/approvals/lab-order/lo2`, () =>
        HttpResponse.json({ error: { code: "LOCKED", message: "already locked", request_id: "r1" } }, { status: 409 }),
      ),
    );

    renderContainer("lo2");
    expect(await screen.findByText("LFT")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /approve lab order/i }));
    await waitFor(() => expect(screen.getByText(/verification complete/i)).toBeTruthy(), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: /confirm approval/i }));

    expect(await screen.findByText(/approved and locked/i)).toBeTruthy();
  });
});
