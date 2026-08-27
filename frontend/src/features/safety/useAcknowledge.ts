import { useCallback, useMemo, useState } from "react";
import type { InteractionPair } from "../../lib/api/endpoints/ml";
import { pairKey } from "./useInteractions";

/**
 * Major interactions block the prescription lock until the doctor
 * acknowledges each one by name. The acknowledgement is deliberately not
 * persisted across a reload: if the page is reloaded the doctor is shown the
 * alerts again, which is the safe direction to fail.
 */
export function useAcknowledge(majorPairs: InteractionPair[]) {
  const [acknowledged, setAcknowledged] = useState<string[]>([]);

  const required = useMemo(
    () => majorPairs.map((p) => pairKey(p.drug_a, p.drug_b)),
    [majorPairs],
  );

  const acknowledge = useCallback((pair: InteractionPair) => {
    const key = pairKey(pair.drug_a, pair.drug_b);
    setAcknowledged((prev) => (prev.includes(key) ? prev : [...prev, key]));
  }, []);

  const isAcknowledged = useCallback(
    (pair: InteractionPair) => acknowledged.includes(pairKey(pair.drug_a, pair.drug_b)),
    [acknowledged],
  );

  const allAcknowledged = required.every((key) => acknowledged.includes(key));

  return {
    acknowledged,
    acknowledge,
    isAcknowledged,
    /** False while any major interaction is still unacknowledged. */
    canLock: allAcknowledged,
    outstanding: required.filter((key) => !acknowledged.includes(key)).length,
  };
}
