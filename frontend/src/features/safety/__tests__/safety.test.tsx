import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { SafetyContainer } from "../SafetyContainer";
import { useAcknowledge } from "../useAcknowledge";
import { pairKey } from "../useInteractions";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";
import type { InteractionPair, InteractionReport } from "../../../lib/api/endpoints/ml";

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

const warfarinAspirin: InteractionPair = {
  drug_a: "Warfarin",
  drug_b: "Aspirin",
  rxcui_a: "11289",
  rxcui_b: "1191",
  severity: "major",
  mechanism: "Additive bleeding risk.",
  evidence_source: "openFDA label",
  url: null,
};

function report(overrides: Partial<InteractionReport> = {}): InteractionReport {
  return {
    pairs: [warfarinAspirin],
    allergy_conflicts: [],
    contraindications: [],
    generated_at: "2026-08-27T09:00:00Z",
    ...overrides,
  };
}

function mockInteractions(body: InteractionReport) {
  server.use(http.post(`${env.apiBase}/api/v1/ml/interactions`, () => HttpResponse.json(body)));
}

function renderSafety(inputs = { medications: ["Warfarin", "Aspirin"], allergies: [], conditions: [] }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SafetyContainer visitId="v-1" inputs={inputs} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("SafetyContainer", () => {
  it("renders a major interaction for a warfarin + aspirin patient", async () => {
    mockInteractions(report());
    renderSafety();

    expect(await screen.findByTestId("interaction-major")).toBeTruthy();
    expect(screen.getByText(/additive bleeding risk/i)).toBeTruthy();
  });

  it("renders allergy conflicts and contraindications alongside interactions", async () => {
    mockInteractions(
      report({
        allergy_conflicts: [
          {
            allergen: "Penicillin",
            drug: "Amoxicillin",
            rxcui: "723",
            rationale: "Same beta-lactam class.",
            source: "openFDA label",
          },
        ],
        contraindications: [
          {
            drug: "Metformin",
            condition: "Stage 4 chronic kidney disease",
            rationale: "Risk of lactic acidosis.",
            source: "ICMR standard treatment guideline",
          },
        ],
      }),
    );
    renderSafety();

    expect(await screen.findByTestId("allergy-conflict")).toBeTruthy();
    expect(screen.getByTestId("contraindication")).toBeTruthy();
  });

  it("says the set is clear rather than rendering nothing", async () => {
    mockInteractions(report({ pairs: [] }));
    renderSafety();

    expect(await screen.findByText(/no interactions, allergy conflicts/i)).toBeTruthy();
  });

  it("never reports an all-clear when the service is down", async () => {
    server.use(
      http.post(`${env.apiBase}/api/v1/ml/interactions`, () =>
        HttpResponse.json(
          { error: { code: "MODEL_UNAVAILABLE", message: "down", request_id: "r" } },
          { status: 503 },
        ),
      ),
    );
    renderSafety();

    expect(await screen.findByText(/safety check unavailable/i)).toBeTruthy();
    expect(screen.queryByText(/no interactions, allergy conflicts/i)).toBeNull();
  });

  it("does not call the service when there is nothing to check", async () => {
    // No handler registered: an unexpected request fails the test outright.
    renderSafety({ medications: [], allergies: [], conditions: [] });
    await waitFor(() => expect(screen.getByText(/no interactions/i)).toBeTruthy());
  });
});

describe("useAcknowledge", () => {
  it("blocks locking until every major interaction is acknowledged", () => {
    const second: InteractionPair = { ...warfarinAspirin, drug_a: "Clopidogrel" };
    const { result } = renderHook(() => useAcknowledge([warfarinAspirin, second]));

    expect(result.current.canLock).toBe(false);
    expect(result.current.outstanding).toBe(2);

    act(() => result.current.acknowledge(warfarinAspirin));
    expect(result.current.canLock).toBe(false);

    act(() => result.current.acknowledge(second));
    expect(result.current.canLock).toBe(true);
    expect(result.current.outstanding).toBe(0);
  });

  it("permits locking when there is no major interaction to acknowledge", () => {
    const { result } = renderHook(() => useAcknowledge([]));
    expect(result.current.canLock).toBe(true);
  });

  it("treats a pair as the same interaction whichever way round it arrives", () => {
    expect(pairKey("Warfarin", "Aspirin")).toBe(pairKey("aspirin", "warfarin"));
  });
});

describe("SafetyContainer acknowledgement", () => {
  it("marks a pair acknowledged once the doctor confirms it", async () => {
    mockInteractions(report());
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    function Harness() {
      const acknowledge = useAcknowledge([warfarinAspirin]);
      return (
        <>
          <span data-testid="can-lock">{String(acknowledge.canLock)}</span>
          <SafetyContainer
            visitId="v-1"
            inputs={{ medications: ["Warfarin", "Aspirin"], allergies: [], conditions: [] }}
            acknowledge={acknowledge}
          />
        </>
      );
    }

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <Harness />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("can-lock").textContent).toBe("false");
    fireEvent.click(await screen.findByRole("button", { name: /acknowledge/i }));
    await waitFor(() => expect(screen.getByTestId("can-lock").textContent).toBe("true"));
  });
});
