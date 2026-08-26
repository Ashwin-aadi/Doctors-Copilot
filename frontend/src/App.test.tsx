import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("redirects to the design preview harness", async () => {
    render(<App />);
    expect(await screen.findByText(/Design Preview/)).toBeTruthy();
  });
});
