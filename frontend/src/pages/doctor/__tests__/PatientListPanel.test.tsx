import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PatientListPanel, type PatientListFilters } from "../PatientListPanel";
import { mockPatientList } from "../../../mocks";

function Wrapper({ onSelect }: { onSelect: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<PatientListFilters>({ colours: [], severities: [] });
  return (
    <PatientListPanel
      patients={mockPatientList}
      selectedId={null}
      onSelect={onSelect}
      search={search}
      onSearchChange={setSearch}
      filters={filters}
      onFilterChange={setFilters}
    />
  );
}

describe("PatientListPanel", () => {
  it("renders a loading skeleton", () => {
    const { container } = render(
      <PatientListPanel
        patients={[]}
        selectedId={null}
        onSelect={() => {}}
        search=""
        onSearchChange={() => {}}
        filters={{ colours: [], severities: [] }}
        onFilterChange={() => {}}
        loading
      />,
    );
    expect(container.querySelector('[role="status"]')).toBeTruthy();
  });

  it("renders an empty state when nothing matches", () => {
    render(
      <PatientListPanel
        patients={[]}
        selectedId={null}
        onSelect={() => {}}
        search=""
        onSearchChange={() => {}}
        filters={{ colours: [], severities: [] }}
        onFilterChange={() => {}}
      />,
    );
    expect(screen.getByText(/no patients match/i)).toBeTruthy();
  });

  it("renders an error state with retry", () => {
    const onRetry = vi.fn();
    render(
      <PatientListPanel
        patients={[]}
        selectedId={null}
        onSelect={() => {}}
        search=""
        onSearchChange={() => {}}
        filters={{ colours: [], severities: [] }}
        onFilterChange={() => {}}
        error="boom"
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("filters by name, mobile, and ABHA ID search", () => {
    render(<Wrapper onSelect={() => {}} />);
    const input = screen.getByPlaceholderText(/search by name/i);
    fireEvent.change(input, { target: { value: "Ananya" } });
    expect(screen.getByText("Ananya Sharma")).toBeTruthy();
    expect(screen.queryByText("Rohit Verma")).toBeNull();

    fireEvent.change(input, { target: { value: "98200 11223" } });
    expect(screen.getByText("Ananya Sharma")).toBeTruthy();

    fireEvent.change(input, { target: { value: "12-9988-7766-5544" } });
    expect(screen.getByText("Fatima Sheikh")).toBeTruthy();
  });

  it("filters by casualty colour chips", () => {
    render(<Wrapper onSelect={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Red" }));
    expect(screen.getByText("Fatima Sheikh")).toBeTruthy();
    expect(screen.queryByText("Karthik Iyer")).toBeNull();
  });

  it("selects a row on Enter for keyboard navigation", () => {
    const onSelect = vi.fn();
    render(<Wrapper onSelect={onSelect} />);
    const row = screen.getByText("Ananya Sharma").closest("tr")!;
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(mockPatientList[0].id);
  });
});
