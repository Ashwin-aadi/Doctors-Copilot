import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Nav } from "../Nav";
import { useAuthStore } from "../../store/auth";
import { initI18n } from "../../lib/i18n";

beforeEach(async () => {
  await initI18n();
  useAuthStore.getState().clear();
});
afterEach(() => cleanup());

function renderNav() {
  return render(
    <MemoryRouter>
      <Nav />
    </MemoryRouter>,
  );
}

describe("Nav", () => {
  it("renders nothing when signed out", () => {
    renderNav();
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("shows patient links for a patient role", () => {
    useAuthStore.setState({
      accessToken: "tok",
      status: "authenticated",
      user: { id: "p1", email: "p@x.in", role: "patient", name: "Asha" },
    });
    renderNav();
    expect(screen.getByText("Symptom Check")).toBeTruthy();
    expect(screen.getByText("Book Appointment")).toBeTruthy();
    expect(screen.queryByText("Queue")).toBeNull();
  });

  it("shows doctor links, derived from role, for a doctor on a patient-only route", () => {
    useAuthStore.setState({
      accessToken: "tok",
      status: "authenticated",
      user: { id: "d1", email: "d@x.in", role: "doctor", name: "Dr. Rao" },
    });
    render(
      <MemoryRouter initialEntries={["/visit/123"]}>
        <Nav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Queue")).toBeTruthy();
    expect(screen.queryByText("Book Appointment")).toBeNull();
  });
});
