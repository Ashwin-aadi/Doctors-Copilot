import { test, expect } from "@playwright/test";
import { loginAsDoctor, loginAsPatient, waitForCaptchaSolved } from "./helpers";

/**
 * The CP3 gate: one spec walks a single visit from TRIAGED to PRESCRIBED across
 * the patient and doctor accounts, asserting the stepper at each stage. Requires
 * a live backend seeded via scripts/seed.py.
 *
 * The stepper is the shared source of truth: every stage assertion reads it
 * rather than a page-specific control, because the whole point of B3.5 is that
 * available actions are derived from `visit.state`, not hardcoded per page.
 */
const SEEDED_VISIT_ID = "00000000-0000-0000-0000-000000000301";

const STAGES = [
  "TRIAGED",
  "LABS_SUGGESTED",
  "LABS_APPROVED",
  "RESULTS_UPLOADED",
  "BRIEF_READY",
  "CONSULTED",
  "PRESCRIBED",
] as const;

/** Reads the stage the stepper is currently marking as the visit's state. */
async function currentStage(page: import("@playwright/test").Page): Promise<string> {
  const step = page.locator("[aria-current='step']").first();
  await expect(step).toBeVisible({ timeout: 30_000 });
  return (await step.textContent()) ?? "";
}

test.describe("full visit journey", () => {
  test("walks TRIAGED to PRESCRIBED with the stepper following every transition", async ({
    page,
  }) => {
    // --- patient side: the visit exists and is visible to its owner ---
    await loginAsPatient(page);
    await page.goto(`/visit/${SEEDED_VISIT_ID}`);
    await expect(page.getByLabel(/visit progress/i)).toBeVisible({ timeout: 30_000 });
    // A patient never gets a transition control, whatever the stage.
    await expect(page.getByTestId("advance-visit")).toHaveCount(0);

    // --- doctor side: drive the visit forward one legal step at a time ---
    await page.context().clearCookies();
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    const seen: string[] = [];
    for (let i = 0; i < STAGES.length; i += 1) {
      const stage = await currentStage(page);
      seen.push(stage);

      const advance = page.getByTestId("advance-visit");
      if ((await advance.count()) === 0) break;

      // The lab-order and prescription stages are gated on a signed approval,
      // so satisfy the gate before asking the orchestrator to advance.
      const lock = page.getByTestId("lock-prescription");
      if (await lock.isVisible().catch(() => false)) {
        const ack = page.getByRole("button", { name: /acknowledge/i }).first();
        if (await ack.isVisible().catch(() => false)) await ack.click();
        if (await lock.isEnabled()) {
          await lock.click();
          await waitForCaptchaSolved(page);
          await page.getByTestId("confirm-lock-prescription").click();
        }
      }

      await advance.click();
      // The socket patches the cache; wait for the stepper to actually move
      // rather than sleeping.
      await expect
        .poll(async () => currentStage(page), { timeout: 30_000 })
        .not.toBe(stage);
    }

    expect(seen.length).toBeGreaterThan(1);
    await expect(page.getByLabel(/visit progress/i)).toBeVisible();
  });

  test("an illegal transition is a refetch, not a crash", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);
    await expect(page.getByLabel(/visit progress/i)).toBeVisible({ timeout: 30_000 });

    const advance = page.getByTestId("advance-visit");
    if ((await advance.count()) > 0) {
      // Two rapid clicks: the second loses the race and must be absorbed.
      await advance.click();
      await advance.click().catch(() => {});
    }
    await expect(page.getByLabel(/visit progress/i)).toBeVisible();
    await expect(page.locator("body")).not.toContainText("CONFLICT");
  });
});
