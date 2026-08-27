import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { provenanceOf, sortByProvenance } from "../provenance";
import { SourceCard } from "../SourceCard";
import type { Citation } from "../../types";

const icmr: Citation = {
  n: 1,
  title: "ICMR Standard Treatment Guidelines: Dengue",
  source: "ICMR",
  url: "https://www.icmr.gov.in/dengue",
  snippet: "Warning signs mandate admission and close monitoring.",
  published: "2019",
};

const who: Citation = {
  n: 2,
  title: "Dengue and severe dengue",
  source: "WHO",
  url: "https://www.who.int/news-room/fact-sheets/detail/dengue",
  snippet: "Dengue is a mosquito-borne viral infection.",
  published: "2024",
};

const openfda: Citation = {
  n: 3,
  title: "Paracetamol label",
  source: "openFDA",
  url: "https://api.fda.gov/drug/label.json",
  snippet: "Hepatotoxicity above the maximum daily dose.",
  published: null,
};

const mohfw: Citation = {
  n: 4,
  title: "MoHFW National Guidelines for Clinical Management of Dengue",
  source: "MoHFW",
  url: "https://www.mohfw.gov.in",
  snippet: "Colour-coded triage at the casualty counter.",
  published: "2023",
};

describe("citation provenance", () => {
  it("identifies the issuing body and its region", () => {
    expect(provenanceOf(icmr)).toMatchObject({ body: "ICMR", region: "IN" });
    expect(provenanceOf(mohfw)).toMatchObject({ body: "MoHFW", region: "IN" });
    expect(provenanceOf(who)).toMatchObject({ body: "WHO", region: "INTL" });
    expect(provenanceOf(openfda)).toMatchObject({ body: "openFDA", region: "INTL" });
  });

  it("ranks ICMR and MoHFW above WHO and openFDA", () => {
    const order = sortByProvenance([openfda, who, mohfw, icmr]).map((c) => c.source);
    expect(order).toEqual(["ICMR", "MoHFW", "WHO", "openFDA"]);
  });

  it("falls back to the raw source name for an unrecognised body", () => {
    const other: Citation = {
      ...icmr,
      title: "Karnataka fever surveillance circular",
      source: "State Health Department",
      url: null,
    };
    expect(provenanceOf(other)).toMatchObject({ body: "State Health Department", region: "INTL" });
  });

  it("SourceCard marks Indian guidance as national and international as a reference", () => {
    const { rerender } = render(<SourceCard citation={icmr} />);
    const indian = screen.getByRole("article");
    expect(within(indian).getByText("ICMR")).toBeTruthy();
    expect(within(indian).getByText("National guidance")).toBeTruthy();

    rerender(<SourceCard citation={who} />);
    const intl = screen.getByRole("article");
    expect(within(intl).getByText("International reference")).toBeTruthy();
  });
});
