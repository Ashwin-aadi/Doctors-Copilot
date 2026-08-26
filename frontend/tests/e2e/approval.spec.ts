import { test, expect } from "@playwright/test";
import { loginAsDoctor } from "./helpers";

/**
 * Requires a live backend seeded via scripts/seed.py, which creates a
 * deterministic TRIAGED visit (id ...000301) for doctor1@demo.example.
 * Unverified on this dev machine: no Python 3.12 + Rust toolchain to run
 * the backend here (see docs/DECISIONS.md, 2026-08-26).
 *
 * Creates a lab order via POST /lab-orders/recommend against that visit
 * (there is no UI surface yet that triggers this -- lab-order creation is
 * still B2 backend-only), then drives the real approval UI: approve with
 * captcha, see the locked state, and confirm a second load of the same
 * order shows the locked state rather than a crash (the "second edit
 * attempt" -- there is nothing left to edit once locked, which is itself
 * the correct behaviour per the CP2 gate).
 */
const VISIT_ID = "00000000-0000-0000-0000-000000000301";

test.describe("approval", () => {
  test("approves a lab order with captcha and locks the UI", async ({ page }) => {
    await loginAsDoctor(page);
    await page.waitForURL(/\/doctor/);

    const recommendRes = await page.request.post("/api/v1/lab-orders/recommend", {
      data: { visit_id: VISIT_ID },
    });
    const { id: labOrderId } = (await recommendRes.json()) as { id: string };

    await page.goto(`/doctor/lab-order/${labOrderId}`);
    await expect(page.getByText(/^draft$/i)).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: /approve lab order/i }).click();
    await expect(page.getByText("Verification complete.")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /confirm approval/i }).click();

    await expect(page.getByText(/approved and locked/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /approve lab order/i })).toHaveCount(0);

    await page.reload();
    await expect(page.getByText(/^approved$/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /approve lab order/i })).toHaveCount(0);
  });
});
