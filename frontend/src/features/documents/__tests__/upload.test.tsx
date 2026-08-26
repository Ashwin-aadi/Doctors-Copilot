import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { UploadContainer } from "../UploadContainer";
import { useAuthStore } from "../../../store/auth";
import { env } from "../../../lib/env";
import { initI18n } from "../../../lib/i18n";
import type { DocumentOut } from "../../../lib/api/endpoints/documents";

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

function renderContainer(patientId = "p1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/doctor/patient/${patientId}`]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/doctor/patient/:id" element={<UploadContainer />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function doneDocument(overrides: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: "doc1",
    patient_id: "p1",
    file_id: "file1",
    status: "done",
    engine: "tesseract",
    mean_confidence: 0.6,
    text: "report text",
    labs: [
      {
        test_name: "Hemoglobin",
        normalized_name: "hemoglobin",
        value: 11.2,
        unit: "g/dL",
        ref_low: 12,
        ref_high: 16,
        flag: "low",
        confidence: 0.55,
      },
    ],
    error: null,
    ...overrides,
  };
}

function selectFile(input: HTMLElement, name: string) {
  const file = new File(["binary"], name, { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("UploadContainer", () => {
  it("uploads a file and shows editable low-confidence lab values once OCR finishes", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/captcha/challenge`, async () =>
        HttpResponse.json(await validCaptchaChallenge()),
      ),
      http.post(`${env.apiBase}/api/v1/files`, () =>
        HttpResponse.json({ id: "file1", patient_id: "p1", mime: "image/png", size: 10, sha256: "abc" }),
      ),
      http.post(`${env.apiBase}/api/v1/documents/upload`, () =>
        HttpResponse.json({ id: "doc1", patient_id: "p1", file_id: "file1", status: "queued", labs: [] }),
      ),
      http.get(`${env.apiBase}/api/v1/documents/doc1`, () => HttpResponse.json(doneDocument())),
    );

    renderContainer();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    selectFile(input, "report.png");

    expect(await screen.findByText("report.png")).toBeTruthy();
    expect(await screen.findByText("Hemoglobin")).toBeTruthy();

    const valueInput = await screen.findByLabelText("Hemoglobin Value");
    expect((valueInput as HTMLInputElement).value).toBe("11.2");
  });

  it("keeps other files uploading when one file fails", async () => {
    let filesCallCount = 0;
    server.use(
      http.get(`${env.apiBase}/api/v1/captcha/challenge`, async () =>
        HttpResponse.json(await validCaptchaChallenge()),
      ),
      // jsdom's XHR doesn't reproduce a browser's auto-computed multipart
      // boundary Content-Type, so msw's request.formData() can't read the
      // uploaded filename here (works fine in real browsers -- verified
      // against Playwright separately). Branch on call order instead: the
      // second concurrent upload is made to fail, independent of which
      // file it turns out to be.
      http.post(`${env.apiBase}/api/v1/files`, async () => {
        filesCallCount += 1;
        if (filesCallCount === 2) {
          return HttpResponse.json(
            { error: { code: "VALIDATION_FAILED", message: "unsupported file", request_id: "r1" } },
            { status: 422 },
          );
        }
        return HttpResponse.json({ id: "file2", patient_id: "p1", mime: "image/png", size: 10, sha256: "def" });
      }),
      http.post(`${env.apiBase}/api/v1/documents/upload`, () =>
        HttpResponse.json({ id: "doc2", patient_id: "p1", file_id: "file2", status: "queued", labs: [] }),
      ),
      http.get(`${env.apiBase}/api/v1/documents/doc2`, () => HttpResponse.json(doneDocument({ id: "doc2" }))),
    );

    renderContainer();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const fileA = new File(["binary"], "a.png", { type: "image/png" });
    const fileB = new File(["binary"], "b.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [fileA, fileB] } });

    await waitFor(() => expect(screen.getAllByText(/failed/i)).toHaveLength(1));
    expect(await screen.findByText("Hemoglobin")).toBeTruthy();
  });

  it("saves an edited lab value and reports when the correction endpoint isn't ready yet", async () => {
    server.use(
      http.get(`${env.apiBase}/api/v1/captcha/challenge`, async () =>
        HttpResponse.json(await validCaptchaChallenge()),
      ),
      http.post(`${env.apiBase}/api/v1/files`, () =>
        HttpResponse.json({ id: "file1", patient_id: "p1", mime: "image/png", size: 10, sha256: "abc" }),
      ),
      http.post(`${env.apiBase}/api/v1/documents/upload`, () =>
        HttpResponse.json({ id: "doc1", patient_id: "p1", file_id: "file1", status: "queued", labs: [] }),
      ),
      http.get(`${env.apiBase}/api/v1/documents/doc1`, () => HttpResponse.json(doneDocument())),
      http.patch(`${env.apiBase}/api/v1/documents/doc1/labs`, () => new HttpResponse(null, { status: 404 })),
    );

    renderContainer();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    selectFile(input, "report.png");

    const valueInput = await screen.findByLabelText("Hemoglobin Value");
    fireEvent.change(valueInput, { target: { value: "11.9" } });

    const saveButton = screen.getByRole("button", { name: /save corrections/i });
    fireEvent.click(saveButton);

    expect(await screen.findByText(/isn't ready yet/i)).toBeTruthy();
  });
});
