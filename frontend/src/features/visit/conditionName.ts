/**
 * The condition a differential names, without its trailing reasoning.
 *
 * The copilot writes a differential as a sentence -- "Dengue fever – supported
 * by thrombocytopenia and Indian epidemiology". Anything downstream that
 * searches on it (the medicine suggester runs a full-text query over drug
 * labels) has to search the name, not the explanation: the filler words match
 * almost every label and drown out the one word that mattered.
 */
const TAIL = /\s+[-–—:(]|\s+\b(?:supported|considered|possible|plausible|likely|given|due)\b/;

export function conditionName(differential: string): string {
  const head = differential.split(TAIL)[0].replace(/[.,;:\s-]+$/, "").trim();
  return head || differential.trim();
}
