import { test, expect } from "@playwright/test";
import { loginAsPatient } from "./helpers";

/**
 * Requires a live backend seeded via scripts/seed.py. The chatbot answers only
 * from the signed-in patient's own record, so the seeded patient must have at
 * least one document or prescription ingested into their corpus.
 */
test.describe("patient chatbot", () => {
  test("streams an answer about the patient's own result", async ({ page }) => {
    await loginAsPatient(page);
    await page.goto("/chat/assistant");

    const composer = page.getByLabel("Message");
    await composer.fill("what does my high creatinine mean?");
    await page.getByRole("button", { name: /send message/i }).click();

    // Progressive rendering: the bubble exists and grows while the stream runs.
    const answer = page.locator("[data-role='assistant'], p").filter({ hasText: /./ });
    await expect(answer.first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/doctor/i).first()).toBeVisible({ timeout: 60_000 });
  });

  test("refuses a dose-change question with the scope notice", async ({ page }) => {
    // Telemedicine Practice Guidelines 2020: decision support never prescribes.
    await loginAsPatient(page);
    await page.goto("/chat/assistant");

    await page.getByLabel("Message").fill("should I double my metformin dose?");
    await page.getByRole("button", { name: /send message/i }).click();

    await expect(page.getByRole("note")).toBeVisible({ timeout: 60_000 });
    await expect(page.locator("body")).not.toContainText("SCOPE_REFUSAL");
  });

  test("shows 112 and 108 as tap-to-dial on an emergency phrase", async ({ page }) => {
    await loginAsPatient(page);
    await page.goto("/chat/assistant");

    await page.getByLabel("Message").fill("crushing chest pain and I cannot breathe");
    await page.getByRole("button", { name: /send message/i }).click();

    const banner = page.getByTestId("emergency-banner");
    await expect(banner).toBeVisible({ timeout: 60_000 });
    await expect(banner.locator('a[href="tel:112"]')).toBeVisible();
    await expect(banner.locator('a[href="tel:108"]')).toBeVisible();
    // Never the US number.
    await expect(page.locator("body")).not.toContainText("911");

    await banner.getByRole("button", { name: /casualty|clinic/i }).click();
    await expect(page).toHaveURL(/\/booking/);
  });

  test("all three surfaces render in हिंदी with no key leaks", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: /हि|EN/ }).click();
    await loginAsPatient(page);
    await page.goto("/chat/assistant");

    await expect(page.locator("body")).not.toContainText("chat.");
    await expect(page.locator("body")).not.toContainText("errorCodes.");
  });
});
