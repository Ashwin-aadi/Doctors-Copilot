import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { VisitContainer } from "../VisitContainer";
import { actionsFor, nextState } from "../useVisit";
import { isNewerFrame, isVisitUpdated } from "../useVisitSocket";

// The live socket is exercised by its own unit tests below; mounting it here
// would open a real WebSocket that msw cannot intercept. Same approach as the
// queue board's tests.
vi.mock("../useVisitSocket", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useVisitSocket")>();
  return { ...actual, useVisitSocket: () => ({ status: "open" as const }) };
});
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

/**
 * The visit surface composes the copilot, safety and prescription containers,
 * so their endpoints have to be stubbed too -- msw is configured to fail the
 * run on any unhandled request, which is what keeps a stray real fetch from
 * silently passing as a green test.
 */
function mockComposedSurfaces() {
  server.use(
    http.post(`${env.apiBase}/api/v1/copilot/brief`, () =>
      HttpResponse.json({
        visit_id: VISIT_ID,
        summary: "No brief for this fixture.",
        differentials: [],
        recommended_procedures: [],
        cautions: [],
        citations: [],
        confidence: 0,
      }),
    ),
    http.post(`${env.apiBase}/api/v1/ml/interactions`, () =>
      HttpResponse.json({
        pairs: [],
        allergy_conflicts: [],
        contraindications: [],
        generated_at: "2026-08-27T09:00:00Z",
      }),
    ),
    http.get(`${env.apiBase}/api/v1/medications/substitutions`, () => HttpResponse.json([])),
    http.get(`${env.apiBase}/api/v1/medications/generic`, () =>
      HttpResponse.json({
        input: "",
        rxcui: null,
        ingredient: "",
        generics: [],
        nlem: false,
        schedule_h: false,
        source_url: null,
        cached: true,
        reasons: [],
      }),
    ),
    http.get(`${env.apiBase}/api/v1/captcha/challenge`, () =>
      HttpResponse.json({ algorithm: "SHA-256", challenge: "x", salt: "s", maxnumber: 1 }),
    ),
    http.get(`${env.apiBase}/api/v1/visits/:id/transcript`, () =>
      HttpResponse.json({ visit_id: VISIT_ID, session_id: null, turns: [] }),
    ),
    http.get(`${env.apiBase}/api/v1/lab-orders/catalog`, () =>
      HttpResponse.json([
        {
          name: "CBC with platelet count",
          loinc: "58410-2",
          default_reason: "Dengue - platelet trend",
          cghs_code: null,
          pmjay_package: null,
        },
      ]),
    ),
    http.get(`${env.apiBase}/api/v1/lab-orders/:id`, () =>
      HttpResponse.json({
        id: "lab-1",
        visit_id: VISIT_ID,
        patient_id: PATIENT_ID,
        status: "draft",
        locked: false,
        items: [{ name: "CBC with platelet count", reason: "Dengue - platelet trend", source: "rule" }],
        approved_by: null,
        approved_at: null,
      }),
    ),
  );
}

function mockVisit(body: VisitOut) {
  mockComposedSurfaces();
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

    // The order is edited in place on the visit now, not behind a link.
    expect(await screen.findByTestId("lab-order-items")).toBeTruthy();
    expect(screen.getByRole("button", { name: /approve lab order/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /advance to/i })).toBeTruthy();
  });

  it("shows the patient each ordered test with its own upload, and what is outstanding", async () => {
    useAuthStore.setState({
      accessToken: "tok",
      status: "authenticated",
      user: { id: "u1", email: "asha@example.in", role: "patient", name: "Asha Kumari" },
    });
    mockVisit(
      // Collecting reports is the "Report uploaded" stage's job -- the stage
      // before it shows what was ordered, read-only.
      visit("RESULTS_UPLOADED", {
        lab_order_id: "lab-1",
        documents: [
          {
            id: "doc-1",
            patient_id: PATIENT_ID,
            file_id: "file-1",
            status: "done",
            labs: [],
            test_name: "CBC with platelet count",
          },
        ],
      } as Partial<VisitOut>),
    );
    // A signed order: two tests, one report already in.
    server.use(
      http.get(`${env.apiBase}/api/v1/lab-orders/:id`, () =>
        HttpResponse.json({
          id: "lab-1",
          visit_id: VISIT_ID,
          patient_id: PATIENT_ID,
          status: "approved",
          locked: true,
          items: [
            { name: "CBC with platelet count", reason: "Dengue - platelet trend", source: "rule" },
            { name: "Dengue NS1 antigen", reason: "Fever under 5 days", source: "rule" },
          ],
          approved_by: "doc-1",
          approved_at: "2026-08-27T09:00:00Z",
        }),
      ),
    );
    renderVisit(`/visit/${VISIT_ID}`);

    const rows = await screen.findAllByTestId("lab-order-test-row");
    expect(rows).toHaveLength(2);
    expect(screen.getByText("1 of 2 uploaded")).toBeTruthy();
    // The outstanding test gets its own labelled control, not a shared dropzone.
    expect(screen.getByLabelText("Upload report for Dengue NS1 antigen")).toBeTruthy();
    // ...and a report already in can be withdrawn.
    expect(screen.getAllByTestId("uploaded-report")).toHaveLength(1);
    expect(
      screen.getByLabelText("Remove the uploaded report for CBC with platelet count"),
    ).toBeTruthy();
  });

  it("sends the visit back when a clinician clicks a stage already passed", async () => {
    mockVisit(visit("CONSULTED"));
    let rewoundTo: string | null = null;
    server.use(
      http.post(`${env.apiBase}/api/v1/visits/:id/rewind`, async ({ request }) => {
        rewoundTo = ((await request.json()) as { target: string }).target;
        return HttpResponse.json(visit("BRIEF_READY"));
      }),
    );
    renderVisit();

    fireEvent.click(await screen.findByRole("button", { name: /Summary ready/i }));
    // Going backwards is confirmed first -- it is a state change other people see.
    fireEvent.click(await screen.findByTestId("confirm-rewind"));

    await waitFor(() => expect(rewoundTo).toBe("BRIEF_READY"));
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
    mockComposedSurfaces();
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

  it("says why an advance was refused instead of failing silently", async () => {
    mockComposedSurfaces();
    server.use(
      http.get(`${env.apiBase}/api/v1/visits/:id`, () => HttpResponse.json(visit("LABS_APPROVED"))),
      http.post(`${env.apiBase}/api/v1/visits/:id/advance`, () =>
        HttpResponse.json(
          {
            error: {
              code: "CONFLICT",
              message: "no completed document for this patient yet",
              request_id: "r",
              details: {},
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

    // The guard names the missing precondition; a button that just stops
    // spinning tells the clinician nothing about what to do next.
    expect(await screen.findByText(/no completed document for this patient yet/i)).toBeTruthy();
  });

  it("drops a refusal when the user moves to another stage", async () => {
    mockComposedSurfaces();
    server.use(
      http.get(`${env.apiBase}/api/v1/visits/:id`, () => HttpResponse.json(visit("LABS_APPROVED"))),
      http.post(`${env.apiBase}/api/v1/visits/:id/advance`, () =>
        HttpResponse.json(
          {
            error: {
              code: "CONFLICT",
              message: "no completed document for this patient yet",
              request_id: "r",
              details: {},
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
    await screen.findByText(/no completed document for this patient yet/i);

    // Previewing a later stage is a different screen; the warning about the
    // stage just left must not follow the user onto it.
    const stepper = within(screen.getByRole("list", { name: "Visit progress" }));
    fireEvent.click(stepper.getByRole("button", { name: /Report uploaded/i }));
    await waitFor(() =>
      expect(screen.queryByText(/no completed document for this patient yet/i)).toBeNull(),
    );
  });

  it("shows the error envelope's code when the visit cannot be read", async () => {
    mockComposedSurfaces();
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

describe("useVisitSocket frame handling", () => {
  it("accepts only frames newer than what the cache holds", () => {
    expect(isNewerFrame("2026-08-27T09:00:00Z", "2026-08-27T09:00:01Z")).toBe(true);
    // A duplicate or a reordered frame must not roll the visit backwards.
    expect(isNewerFrame("2026-08-27T09:00:00Z", "2026-08-27T09:00:00Z")).toBe(false);
    expect(isNewerFrame("2026-08-27T09:00:00Z", "2026-08-27T08:59:59Z")).toBe(false);
    // Nothing cached yet: take the frame.
    expect(isNewerFrame(undefined, "2026-08-27T09:00:00Z")).toBe(true);
  });

  it("ignores frames that are not a visit update", () => {
    expect(isVisitUpdated({ type: "heartbeat" })).toBe(false);
    expect(isVisitUpdated(null)).toBe(false);
    expect(
      isVisitUpdated({ visit_id: VISIT_ID, state: "CONSULTED", updated_at: "2026-08-27T09:00:00Z" }),
    ).toBe(true);
  });
});
