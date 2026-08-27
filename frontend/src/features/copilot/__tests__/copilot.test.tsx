import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { CopilotContainer } from "../CopilotContainer";
import { splitCitationMarkers } from "../useCitations";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";
import type { Citation } from "../../../lib/api/endpoints/copilot";

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

function renderContainer(visitId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <CopilotContainer visitId={visitId} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function envelope(code: string, message: string) {
  return { error: { code, message, request_id: "req-brief", details: {} } };
}

const citations: Citation[] = [
  { n: 1, title: "NMC Guideline", source: "NMC", snippet: "Refer for chest pain.", url: null, published: null },
];

describe("splitCitationMarkers", () => {
  it("splits inline [n] markers into text and citation segments", () => {
    const segments = splitCitationMarkers("Consider referral [1] given the history.", citations);
    expect(segments).toEqual([
      { type: "text", value: "Consider referral " },
      { type: "citation", n: 1, citation: citations[0] },
      { type: "text", value: " given the history." },
    ]);
  });

  it("passes through text with no markers unchanged", () => {
    expect(splitCitationMarkers("no markers here", [])).toEqual([{ type: "text", value: "no markers here" }]);
  });
});

describe("CopilotContainer", () => {
  it("renders the brief and opens the source drawer on citation click", async () => {
    server.use(
      http.post(`${env.apiBase}/api/v1/copilot/brief`, () =>
        HttpResponse.json({
          visit_id: "v1",
          summary: "Likely viral pharyngitis [1].",
          differentials: [],
          recommended_procedures: [],
          cautions: [],
          citations,
          confidence: 0.82,
        }),
      ),
    );

    renderContainer("v1");

    expect(await screen.findByText(/Likely viral pharyngitis/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("View source 1"));
    expect(await screen.findByText("NMC Guideline")).toBeTruthy();
  });

  it("shows the extractive fallback notice when no citations are returned", async () => {
    server.use(
      http.post(`${env.apiBase}/api/v1/copilot/brief`, () =>
        HttpResponse.json({
          visit_id: "v1",
          summary: "Summary with no sources.",
          differentials: [],
          recommended_procedures: [],
          cautions: [],
          citations: [],
          confidence: 0.9,
        }),
      ),
    );

    renderContainer("v1");
    expect(await screen.findByText(/no external sources/i)).toBeTruthy();
  });

  it("shows a retry action instead of crashing when the model is unavailable", async () => {
    server.use(
      http.post(`${env.apiBase}/api/v1/copilot/brief`, () =>
        HttpResponse.json(envelope("MODEL_UNAVAILABLE", "model down"), { status: 503 }),
      ),
    );

    renderContainer("v1");
    expect(await screen.findByText(/AI assistance is temporarily unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
  });

  it("flags a low-confidence brief without hiding the panel", async () => {
    server.use(
      http.post(`${env.apiBase}/api/v1/copilot/brief`, () =>
        HttpResponse.json({
          visit_id: "v1",
          summary: "Uncertain presentation.",
          differentials: [],
          recommended_procedures: [],
          cautions: [],
          citations: [],
          confidence: 0.2,
        }),
      ),
    );

    renderContainer("v1");
    await waitFor(() => expect(screen.getByText("Low confidence")).toBeTruthy());
    expect(screen.getByText(/Uncertain presentation/)).toBeTruthy();
  });
});
