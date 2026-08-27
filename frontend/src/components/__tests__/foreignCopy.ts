/**
 * The India copy lint greps the whole of `src/` for foreign framing, so a test
 * that asserts "this string must never appear" cannot spell the string out --
 * it would trip the very lint it exists to protect. The tokens are assembled
 * from character codes instead, and named for what they are.
 */
const token = (...codes: number[]): string => String.fromCharCode(...codes);

/** The US emergency number. Indian copy uses 112, or 108 for an ambulance. */
export const FOREIGN_EMERGENCY_NUMBER = new RegExp(token(57, 49, 49));

/** The US health privacy law. Indian copy follows the DPDP Act 2023. */
export const FOREIGN_PRIVACY_LAW = new RegExp(token(72, 73, 80, 65, 65), "i");

/** US payer framing. Indian copy says consultation fee and PM-JAY. */
export const FOREIGN_PAYER_FRAMING = new RegExp(
  [token(99, 111, 112, 97, 121), token(105, 110, 115, 117, 114, 97, 110, 99, 101)].join("|"),
  "i",
);

/** The US abbreviation for the emergency department; Indian copy says casualty. */
export const FOREIGN_CASUALTY_ABBREVIATION = new RegExp(`\\b${token(69, 82)}\\b`);

/** Dollar amounts. Every price in this product is in rupees. */
export const FOREIGN_CURRENCY = /\$[0-9]/;
