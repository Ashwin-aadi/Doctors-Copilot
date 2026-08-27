import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { VisitContainer } from "../VisitContainer";
import { actionsFor, nextState } from "../useVisit";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";
import type { VisitOut, VisitState } from "../../../lib/api/endpoints/visits";

const server = setupServer();

beforeAll(async () => {
  await initI18n();
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const VISIT_ID = "00000000-0000-0000-0000-000000000301";
const PATIENT_ID = "00000000-0000-0000-0000-000000000101";

beforeEach(() => {
  useAuthStore.getState().clear();
  useAuthStore.setState({
    accessToken: "tok",
    status: "authenticated",
    user: { id: "d1", email: "doc@clinic.in", role: "doctor", name: "Dr. Rao", doctorId: "doc-1" },
  });
});

function visit(state: VisitState, overrides: Partial<VisitOut> = {}): VisitOut {
  return {
    id: VISIT_ID,
    patient_id: PATIENT_ID,
    doctor_id: "doc-1",
    state,
    triage: null,
    lab_order_id: null,
    documents: [],
    brief: null,
    safety: null,
    queue: null,
    updated_at: "2026-08-27T09:00:00Z",
    ...overrides,
  } as VisitOut;
}

function mockVisit(body: VisitOut) {
  server.use(
    http.get(`${env.apiBase}/api/v1/visits/:id`, () => HttpResponse.json(body)),
    http.get(`${env.apiBase}/api/v1/patients/:id`, () =>
      HttpResponse.json({
        id: PATIENT_ID,
        name: "Asha Kumari",
        allergies: [],
        conditions: [],
        medications: [],
        abha_id: null,
      }),
    ),
  );
}

function renderVisit(path = `/doctor/visit/${VISIT_ID}`) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/doctor/visit/:id" element={<VisitContainer />} />
          <Route path="/visit/:id" element={<VisitContainer />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("visit state machine", () => {
  it("orders the states as the orchestrator does", () => {
    expect(nextState("TRIAGED")).toBe("LABS_SUGGESTED");
    expect(nextState("BRIEF_READY")).toBe("CONSULTED");
    expect(nextState("PRESCRIBED")).toBeNull();
  });

  it("derives the available actions from the state, never the page", () => {
    expect(actionsFor("LABS_SUGGESTED").canApproveLabOrder).toBe(true);
    expect(actionsFor("LABS_SUGGESTED").canPrescribe).toBe(false);
    expect(actionsFor("LABS_APPROVED").canUploadDocuments).toBe(true);
    expect(actionsFor("RESULTS_UPLOADED").canBuildBrief).toBe(true);
    expect(actionsFor("CONSULTED").canPrescribe).toBe(true);
    expect(actionsFor("TRIAGED").canBuildBrief).toBe(false);
  });
});

describe("VisitContainer", () => {
  it("renders the stepper at the visit's live state", async () => {
    mockVisit(visit("LABS_SUGGESTED", { lab_order_id: "lab-1" }));
    renderVisit();

    expect(await screen.findByTestId("visit-lab-order-link")).toBeTruthy();
    expect(screen.getByRole("button", { name: /advance to/i })).toBeTruthy();
  });

  it("offers the next transition to a clinician", async () => {
    mockVisit(visit("BRIEF_READY"));
    renderVisit();
    expect(await screen.findByTestId("advance-visit")).toBeTruthy();
  });

  it("never offers a transition to the patient viewing their own visit", async () => {
    useAuthStore.setState({
      accessToken: "tok",
      status: "authenticated",
      user: {
        id: "u2",
        email: "asha@example.in",
        role: "patient",
        name: "Asha",
        patientId: PATIENT_ID,
      },
    });
    mockVisit(visit("BRIEF_READY"));
    renderVisit(`/visit/${VISIT_ID}`);

    // The stepper proves the visit rendered; the action must still be absent.
    expect(await screen.findByLabelText(/visit progress/i)).toBeTruthy();
    expect(screen.queryByTestId("advance-visit")).toBeNull();
  });

  it("refetches instead of erroring when someone else advanced the visit first", async () => {
    let calls = 0;
    server.use(
      http.get(`${env.apiBase}/api/v1/visits/:id`, () => {
        calls += 1;
        // Second read reflects the state the other actor moved it to.
        return HttpResponse.json(visit(calls === 1 ? "BRIEF_READY" : "CONSULTED"));
      }),
      http.post(`${env.apiBase}/api/v1/visits/:id/advance`, () =>
        HttpResponse.json(
          {
            error: {
              code: "CONFLICT",
              message: "precondition for this transition is not met",
              request_id: "r",
              details: { from: "CONSULTED", to: "CONSULTED" },
            },
          },
          { status: 409 },
        ),
      ),
      http.get(`${env.apiBase}/api/v1/patients/:id`, () =>
        HttpResponse.json({ id: PATIENT_ID, name: "Asha", allergies: [], conditions: [], medications: [] }),
      ),
    );

    renderVisit();
    fireEvent.click(await screen.findByTestId("advance-visit"));

    // The container must not surface an error page for a lost race.
    await waitFor(() => expect(calls).toBeGreaterThan(1));
    expect(screen.queryByText(/CONFLICT/)).toBeNull();
  });

  it("shows the error envelope's code when the visit cannot be read", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/visits/:id`, () =>
        HttpResponse.json(
          { error: { code: "AUTH_FORBIDDEN", message: "not your visit", request_id: "r" } },
          { status: 403 },
        ),
      ),
    );
    renderVisit();

    expect(await screen.findByText(/don.t have permission/i)).toBeTruthy();
  });
});
