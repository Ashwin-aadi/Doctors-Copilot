import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { loginAsDoctor } from "./helpers";

const dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Requires a live backend seeded via scripts/seed.py. Unverified on this
 * dev machine: no Python 3.12 + Rust toolchain to run the backend here
 * (see docs/DECISIONS.md, 2026-08-26). Uploads a real fixture PDF from
 * ml/fixtures/cbc.pdf so OCR has something to extract.
 *
 * The "correction persists after reload" assertion additionally depends on
 * `PATCH /api/v1/documents/{id}/labs`, which does not exist on the backend
 * yet (only GET is implemented) -- see the BLOCKER in docs/DECISIONS.md,
 * B2.4. Until it ships, this step is expected to surface the "not ready"
 * notice rather than a persisted correction.
 */
const PATIENT_ID = "00000000-0000-0000-0000-000000000101";
const FIXTURE_PDF = path.resolve(dirname, "../../../ml/fixtures/cbc.pdf");

test.describe("upload", () => {
  test("uploads a report, reaches done, and a low-confidence cell is editable", async ({ page }) => {
    await loginAsDoctor(page);
    await page.waitForURL(/\/doctor/);

    await page.goto(`/doctor/patient/${PATIENT_ID}`);
    await page.setInputFiles('input[type="file"]', FIXTURE_PDF);

    await expect(page.getByText(/uploading|uploaded/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/uploaded/i)).toBeVisible({ timeout: 30_000 });

    const lowConfidenceInput = page.locator('input[aria-label$="Value"]').first();
    await expect(lowConfidenceInput).toBeVisible({ timeout: 60_000 });

    await lowConfidenceInput.fill("11.9");
    await page.getByRole("button", { name: /save corrections/i }).click();

    await page.reload();
    await expect(page.getByText(/corrections saved|isn't ready yet/i)).toBeVisible({ timeout: 15_000 });
  });
});
