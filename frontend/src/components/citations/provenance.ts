import type { Citation } from "../types";

export type ProvenanceRegion = "IN" | "INTL";

export interface Provenance {
  /** Short name of the issuing body, as a doctor would recognise it. */
  body: string;
  region: ProvenanceRegion;
  /** Lower sorts first. Indian national guidance outranks international. */
  rank: number;
}

/**
 * An Indian doctor needs to see at a glance whether a recommendation follows
 * the national protocol, so national bodies are ranked ahead of international
 * ones. International pharmacology sources are kept -- interaction chemistry is
 * universal -- but they never lead.
 */
const BODIES: Array<{ match: RegExp; body: string; region: ProvenanceRegion; rank: number }> = [
  { match: /icmr/i, body: "ICMR", region: "IN", rank: 0 },
  { match: /mohfw|ministry of health/i, body: "MoHFW", region: "IN", rank: 1 },
  { match: /ncdc/i, body: "NCDC", region: "IN", rank: 2 },
  { match: /ncvbdc|vector.?borne/i, body: "NCVBDC", region: "IN", rank: 3 },
  { match: /ntep|tbcindia|tuberculosis programme/i, body: "NTEP", region: "IN", rank: 4 },
  { match: /nhm|national health mission/i, body: "NHM", region: "IN", rank: 5 },
  { match: /cdsco/i, body: "CDSCO", region: "IN", rank: 6 },
  { match: /janaushadhi|jan aushadhi/i, body: "Jan Aushadhi", region: "IN", rank: 7 },
  { match: /nlem|essential medicines/i, body: "NLEM", region: "IN", rank: 8 },
  { match: /who|world health/i, body: "WHO", region: "INTL", rank: 20 },
  { match: /openfda|fda\.gov/i, body: "openFDA", region: "INTL", rank: 21 },
  { match: /rxnorm|rxnav|nlm/i, body: "RxNorm", region: "INTL", rank: 22 },
  { match: /pubmed/i, body: "PubMed", region: "INTL", rank: 23 },
  { match: /medlineplus/i, body: "MedlinePlus", region: "INTL", rank: 24 },
];

export function provenanceOf(citation: Pick<Citation, "source" | "url" | "title">): Provenance {
  const haystack = `${citation.source} ${citation.url ?? ""} ${citation.title}`;
  const hit = BODIES.find((b) => b.match.test(haystack));
  if (hit) return { body: hit.body, region: hit.region, rank: hit.rank };
  return { body: citation.source, region: "INTL", rank: 50 };
}

/** Indian guidance first, then international, stable within each group. */
export function sortByProvenance<T extends Pick<Citation, "source" | "url" | "title">>(items: T[]): T[] {
  return [...items].sort((a, b) => provenanceOf(a).rank - provenanceOf(b).rank);
}
