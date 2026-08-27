import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ChatbotContainer } from "../ChatbotContainer";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";

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
    user: {
      id: "u1",
      email: "asha@example.in",
      role: "patient",
      name: "Asha",
      patientId: "p-1",
    },
  });
});

/** Builds an SSE body from the frames the backend would emit, in order. */
function sseBody(frames: Array<{ event: string; data: unknown }>): string {
  return frames.map((f) => `event: ${f.event}\ndata: ${JSON.stringify(f.data)}\n\n`).join("");
}

function mockChat(frames: Array<{ event: string; data: unknown }>) {
  server.use(
    http.post(`${env.apiBase}/api/v1/chat/patient`, () =>
      HttpResponse.text(sseBody(frames), {
        headers: { "Content-Type": "text/event-stream" },
      }),
    ),
  );
}

function renderChat() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ChatbotContainer />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function ask(question: string) {
  const box = screen.getByRole("textbox");
  fireEvent.change(box, { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatbotContainer", () => {
  it("renders the streamed answer and its citations", async () => {
    mockChat([
      { event: "token", data: { text: "Your creatinine is a little high [1]. " } },
      { event: "token", data: { text: "Please discuss this with your doctor." } },
      {
        event: "citation",
        data: {
          n: 1,
          title: "Kidney function tests",
          source: "MedlinePlus",
          snippet: "Creatinine measures kidney function.",
          url: null,
          published: null,
        },
      },
      { event: "done", data: { confidence: 0.72 } },
    ]);

    renderChat();
    await ask("what does my high creatinine mean?");

    await waitFor(() =>
      expect(screen.getByText(/creatinine is a little high/i)).toBeTruthy(),
    );
    expect(screen.getByText(/discuss this with your doctor/i)).toBeTruthy();
  });

  it("renders the scope-refusal notice instead of a bubble for a dose question", async () => {
    // Telemedicine Practice Guidelines 2020: the bot may explain, never prescribe.
    mockChat([
      {
        event: "token",
        data: { text: "SCOPE_REFUSAL I cannot advise on changing a dose." },
      },
      { event: "done", data: { confidence: 1 } },
    ]);

    renderChat();
    await ask("should I double my metformin dose?");

    await waitFor(() => expect(screen.getByRole("note")).toBeTruthy());
    expect(screen.queryByText(/SCOPE_REFUSAL/)).toBeNull();
    expect(screen.getByText(/can.t advise on starting, stopping or changing a dose/i)).toBeTruthy();
  });

  it("mounts the emergency banner with 112 and 108 when the guardrail fires", async () => {
    mockChat([
      {
        event: "token",
        data: { text: "[[EMERGENCY]] This needs urgent medical attention." },
      },
      { event: "done", data: { confidence: 1 } },
    ]);

    renderChat();
    await ask("severe chest pain and I cannot breathe");

    await waitFor(() => expect(screen.getByTestId("emergency-banner")).toBeTruthy());
    const banner = screen.getByTestId("emergency-banner");
    expect(banner.querySelector('a[href="tel:112"]')).toBeTruthy();
    expect(banner.querySelector('a[href="tel:108"]')).toBeTruthy();
    // Never the US number.
    expect(banner.textContent).not.toMatch(/911/);
    // The marker itself is an internal signal and must never be shown.
    expect(screen.queryByText(/\[\[EMERGENCY\]\]/)).toBeNull();
  });

  it("surfaces a cross-patient read as an error rather than rendering an answer", async () => {
    server.use(
      http.post(`${env.apiBase}/api/v1/chat/patient`, () =>
        HttpResponse.json(
          {
            error: {
              code: "AUTH_FORBIDDEN",
              message: "you may only read your own records",
              request_id: "r-1",
            },
          },
          { status: 403 },
        ),
      ),
    );

    renderChat();
    await ask("show me another patient's report");

    await waitFor(() => expect(screen.getByText("AUTH_FORBIDDEN")).toBeTruthy());
  });
});
