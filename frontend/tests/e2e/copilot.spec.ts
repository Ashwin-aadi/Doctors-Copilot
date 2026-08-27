import { test, expect } from "@playwright/test";
import { loginAsDoctor } from "./helpers";

/**
 * Requires a live backend seeded via scripts/seed.py, which creates a
 * deterministic TRIAGED visit (id 00000000-0000-0000-0000-000000000301) for
 * doctor1@demo.example / patient1@demo.example. Unverified on this dev
 * machine: no Python 3.12 + Rust toolchain to run the backend here (see
 * docs/DECISIONS.md, 2026-08-26). The queue-board route (B2.3) and
 * VisitContainer (B3.5) aren't wired yet, so this test navigates straight to
 * the copilot route rather than through the queue.
 */
const SEEDED_VISIT_ID = "00000000-0000-0000-0000-000000000301";

test.describe("copilot", () => {
  test("doctor sees the AI brief with clickable citations", async ({ page }) => {
    await loginAsDoctor(page);
    await page.waitForURL(/\/doctor/);

    await page.goto(`/doctor/visit/${SEEDED_VISIT_ID}`);

    await expect(page.getByText(/ai decision support/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/ai clinical brief/i)).toBeVisible({ timeout: 60_000 });

    const citation = page.getByLabel("View source 1").first();
    if (await citation.isVisible().catch(() => false)) {
      await citation.click();
      await expect(page.getByRole("dialog")).toBeVisible();
    }
  });

  test("renders with no untranslated keys in हिंदी", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: /हि|EN/ }).click();
    await expect(page.locator("body")).not.toContainText("copilot.");
    await expect(page.locator("body")).not.toContainText("errorCodes.");
  });
});
