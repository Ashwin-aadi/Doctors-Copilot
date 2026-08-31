import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../../components/ui/Toast";
import { AppRouter } from "../index";
import { useAuthStore } from "../../store/auth";
import { initI18n } from "../../lib/i18n";

/** Renders the current path, so a test can assert on a redirect rather than
 * on the absence of a lazily-loaded screen (which is absent either way for
 * the first frame). */
function LocationProbe() {
  return <span data-testid="pathname">{useLocation().pathname}</span>;
}

function renderAt(path: string) {
  const client = new QueryClient();
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <QueryClientProvider client={client}>
          <LocationProbe />
          <AppRouter />
        </QueryClientProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

beforeAll(async () => {
  await initI18n();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("network disabled in this test"))),
  );
});

beforeEach(() => {
  useAuthStore.getState().clear();
});

describe("router", () => {
  it("renders the login page at /login", async () => {
    renderAt("/login");
    expect(await screen.findByRole("heading", { name: /log in/i })).toBeTruthy();
  });

  it("redirects an anonymous visitor away from a patient-only route", async () => {
    renderAt("/chat");
    expect(await screen.findByRole("heading", { name: /log in/i })).toBeTruthy();
  });

  it("sends a signed-in user asking for /register to their own home", async () => {
    useAuthStore.getState().setSession(
      { id: "u1", email: "doctor1@demo.example", role: "doctor", name: "Dr. Ananya Rao" },
      "token",
    );
    renderAt("/register");
    await waitFor(() => expect(screen.getByTestId("pathname").textContent).toBe("/doctor"));
  });

  it("shows Not Found for an unknown path", async () => {
    renderAt("/this-route-does-not-exist");
    expect(await screen.findByText(/page not found/i)).toBeTruthy();
  });
});
