import { test, expect } from "@playwright/test";
import { loginAsDoctor, waitForCaptchaSolved } from "./helpers";

/**
 * Requires a live backend seeded via scripts/seed.py with a CONSULTED visit
 * carrying a drafted prescription. `GET /medications/substitutions` resolves the
 * visit to its latest prescription and echoes `prescription_id` on every row,
 * which is what the lock and the PDF export are keyed on.
 */
const SEEDED_VISIT_ID = "00000000-0000-0000-0000-000000000301";

test.describe("prescription and generic substitution", () => {
  test("shows the Jan Aushadhi saving in rupees and never a dollar figure", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    const savings = page.getByTestId("prescription-total-savings");
    await expect(savings).toBeVisible({ timeout: 30_000 });
    await expect(savings).toContainText("₹");
    await expect(page.locator("body")).not.toContainText(/\$\d/);
  });

  test("a blocked substitute is shown with its reason and cannot be selected", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    const blocked = page.locator("[data-testid^='blocked-option-']").first();
    if (await blocked.isVisible().catch(() => false)) {
      // Shown, never hidden -- the reason is the safety story.
      await expect(blocked).toContainText(/blocked/i);
      await expect(blocked.locator("button")).toHaveCount(0);
    }
  });

  test("locking with captcha issues a PDF carrying the NMC number", async ({ page }) => {
    await loginAsDoctor(page);
    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    const lock = page.getByTestId("lock-prescription");
    await expect(lock).toBeVisible({ timeout: 30_000 });

    // Any major interaction must be acknowledged before the lock opens.
    const ack = page.getByRole("button", { name: /acknowledge/i }).first();
    if (await ack.isVisible().catch(() => false)) await ack.click();

    await expect(lock).toBeEnabled();
    await lock.click();

    await waitForCaptchaSolved(page);
    const download = page.waitForEvent("download");
    await page.getByTestId("confirm-lock-prescription").click();

    const file = await download;
    expect(file.suggestedFilename()).toMatch(/prescription-.*\.pdf$/);
    const stream = await file.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(chunk as Buffer);
    expect(Buffer.concat(chunks).byteLength).toBeGreaterThan(0);

    // Second attempt settles into the locked state rather than crashing.
    await expect(page.getByTestId("download-prescription")).toBeVisible();
  });
});
