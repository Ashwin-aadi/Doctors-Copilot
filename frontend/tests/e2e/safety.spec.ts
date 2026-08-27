import { test, expect } from "@playwright/test";
import { loginAsDoctor } from "./helpers";

/**
 * Requires a live backend seeded via scripts/seed.py with a patient carrying an
 * interacting medication set (warfarin + aspirin). The safety surface is
 * doctor-only: `/ml/interactions` and `/medications/substitutions` both reject a
 * patient token.
 */
const SEEDED_VISIT_ID = "00000000-0000-0000-0000-000000000301";

test.describe("safety surfaces", () => {
  test("a major interaction blocks the prescription lock until acknowledged", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    const alert = page.getByTestId("interaction-major").first();
    await expect(alert).toBeVisible({ timeout: 30_000 });

    const lock = page.getByTestId("lock-prescription");
    await expect(lock).toBeDisabled();
    await expect(page.getByTestId("acknowledgement-required")).toBeVisible();

    await page.getByRole("button", { name: /acknowledge/i }).first().click();
    await expect(lock).toBeEnabled();
  });

  test("the same alert is not duplicated across surfaces on one visit", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    await expect(page.getByTestId("interaction-major").first()).toBeVisible({ timeout: 30_000 });
    // Copilot panel and prescription builder share one query key, so the report
    // is fetched once and each pair rendered once.
    const rendered = await page.getByTestId("interaction-major").count();
    expect(rendered).toBeLessThanOrEqual(1);
  });

  test("the decision-support banner stays mounted alongside the alerts", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    await expect(page.getByText(/decision support/i).first()).toBeVisible({ timeout: 30_000 });
  });
});
