import type { GenericOption } from "../types";

/**
 * What the patient actually pays at the counter. `mrpInr` is the branded MRP --
 * what they would have paid without substituting -- so it is only a fallback,
 * never the headline price.
 */
export function effectivePrice(option: GenericOption): number | null {
  return option.priceInr ?? option.mrpInr ?? null;
}

/**
 * The NPPA ceiling is frequently *equal* to the price, because where a notified
 * ceiling exists it is used as the price. Showing both as though they were
 * independent numbers that happen to agree is misleading, so the cap line only
 * appears when it actually differs.
 */
export function capWorthShowing(option: GenericOption, price: number | null): boolean {
  return option.nppaCeilingInr != null && option.nppaCeilingInr !== price;
}
