import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { PrescriptionContainer } from "../PrescriptionContainer";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";
import type { SubstitutionRow } from "../../../lib/api/endpoints/medications";
import type { InteractionReport } from "../../../lib/api/endpoints/ml";

const server = setupServer();

beforeAll(async () => {
  await initI18n();
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  server.resetHandlers();
  vi.unstubAllGlobals();
});
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.getState().clear();
  useAuthStore.setState({
    accessToken: "tok",
    status: "authenticated",
    user: { id: "d1", email: "doc@clinic.in", role: "doctor", name: "Dr. Rao", doctorId: "doc-1" },
  });
});

const PRESCRIPTION_ID = "00000000-0000-0000-0000-000000000401";

const row: SubstitutionRow = {
  prescription_id: PRESCRIPTION_ID,
  original: "Dolo 650",
  ingredient: "Paracetamol",
  options: [
    {
      name: "Paracetamol 650mg tablet",
      rxcui: "161",
      form: "tablet",
      strength: "650 mg",
      tty: "SCD",
      jan_aushadhi_code: "JA-0231",
      mrp_inr: 30,
      price_inr: 12,
      nppa_ceiling_inr: 12,
      savings_pct: 60,
    },
  ],
  blocked: [
    {
      name: "Nimesulide 100mg tablet",
      rxcui: null,
      reason: "Not an equivalent medicine for this ingredient.",
      severity: "not_equivalent",
      source_url: null,
    },
  ],
  total_savings_inr: 18,
  reasons: ["Available at a Jan Aushadhi Kendra", "Saves Rs 18 (60%)"],
  reasons_hi: [],
};

const cleanReport: InteractionReport = {
  pairs: [],
  allergy_conflicts: [],
  contraindications: [],
  generated_at: "2026-08-27T09:00:00Z",
};

function mockBackend(options: { report?: InteractionReport; rows?: SubstitutionRow[] } = {}) {
  server.use(
    http.get(`${env.apiBase}/api/v1/medications/substitutions`, () =>
      HttpResponse.json(options.rows ?? [row]),
    ),
    http.get(`${env.apiBase}/api/v1/medications/generic`, () =>
      HttpResponse.json({
        input: "Dolo 650",
        rxcui: "161",
        ingredient: "Paracetamol",
        generics: [],
        nlem: true,
        schedule_h: true,
        source_url: null,
        cached: true,
        reasons: [],
      }),
    ),
    http.post(`${env.apiBase}/api/v1/ml/interactions`, () =>
      HttpResponse.json(options.report ?? cleanReport),
    ),
    // A genuinely solvable proof-of-work challenge: sha256("salt-" + 7).
    http.get(`${env.apiBase}/api/v1/captcha/challenge`, () =>
      HttpResponse.json({
        algorithm: "SHA-256",
        challenge: "03481f41786f493bd74b33974ff30486eab518551e21f2459850785e88dfd763",
        salt: "salt-",
        maxnumber: 20,
      }),
    ),
  );
}

function renderPrescription() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <PrescriptionContainer visitId="v-1" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("PrescriptionContainer", () => {
  it("shows the Jan Aushadhi option with its rupee saving", async () => {
    mockBackend();
    renderPrescription();

    expect(await screen.findByText(/Paracetamol 650mg tablet/)).toBeTruthy();
    // Indian digit grouping and the rupee sign, never a dollar figure.
    expect(screen.getByTestId("prescription-total-savings").textContent).toMatch(/₹/);
    expect(document.body.textContent).not.toMatch(/\$\d/);
  });

  it("renders a blocked substitute with its reason and never as a choice", async () => {
    mockBackend();
    renderPrescription();

    const blocked = await screen.findByText(/Not an equivalent medicine/);
    expect(blocked).toBeTruthy();
    // The blocked item must not be offered as a selectable option.
    expect(screen.queryByRole("button", { name: /Nimesulide/i })).toBeNull();
  });

  it("surfaces the Schedule H statutory warning for a scheduled drug", async () => {
    mockBackend();
    renderPrescription();

    expect(await screen.findByTestId("schedule-warning-Dolo 650")).toBeTruthy();
  });

  it("blocks locking until a major interaction is acknowledged", async () => {
    mockBackend({
      report: {
        ...cleanReport,
        pairs: [
          {
            drug_a: "Warfarin",
            drug_b: "Aspirin",
            rxcui_a: null,
            rxcui_b: null,
            severity: "major",
            mechanism: "Additive bleeding risk.",
            evidence_source: "openFDA label",
            url: null,
          },
        ],
      },
    });
    renderPrescription();

    const lock = await screen.findByTestId("lock-prescription");
    await waitFor(() => expect(lock.hasAttribute("disabled")).toBe(true));
    expect(screen.getByTestId("acknowledgement-required")).toBeTruthy();

    fireEvent.click(await screen.findByRole("button", { name: /acknowledge/i }));
    await waitFor(() => expect(lock.hasAttribute("disabled")).toBe(false));
  });

  it("enables locking straight away when nothing major is outstanding", async () => {
    mockBackend();
    renderPrescription();

    const lock = await screen.findByTestId("lock-prescription");
    await waitFor(() => expect(lock.hasAttribute("disabled")).toBe(false));
    expect(screen.queryByTestId("acknowledgement-required")).toBeNull();
  });

  it("settles into the locked state when someone else locked it first", async () => {
    mockBackend();
    server.use(
      http.post(`${env.apiBase}/api/v1/approvals/prescription/:id`, () =>
        HttpResponse.json(
          { error: { code: "LOCKED", message: "already locked", request_id: "r" } },
          { status: 409 },
        ),
      ),
    );
    renderPrescription();

    fireEvent.click(await screen.findByTestId("lock-prescription"));
    // The captcha widget solves in-browser; drive the mutation directly once
    // the modal is open by dispatching on the confirm button after the token
    // lands, which is what a doctor does a moment later.
    const confirm = await screen.findByTestId("confirm-lock-prescription");
    await waitFor(() => expect(confirm.hasAttribute("disabled")).toBe(false), { timeout: 15_000 });
    fireEvent.click(confirm);

    await waitFor(() => expect(screen.getByTestId("download-prescription")).toBeTruthy());
  }, 20_000);
});
