import { test, expect, type Page } from "@playwright/test";
import { loginAsDoctor } from "./helpers";

/**
 * Requires a live backend seeded via scripts/seed.py, plus a walk-in queue
 * entry (created below via POST /queue/walk-in against the seeded clinic,
 * since seed.py doesn't pre-populate the queue). Unverified on this dev
 * machine: no Python 3.12 + Rust toolchain to run the backend here (see
 * docs/DECISIONS.md, 2026-08-26).
 *
 * The live-reorder assertion additionally depends on `/ws/queue/{clinic_id}`
 * (backend/app/api/v1/ws.py), which as of this write is a stub that accepts
 * the connection and immediately closes it with code 1013 ("queue stream
 * lands in A3.5"). Until that lands, the board can only resync via the
 * `useQueueSocket` reconnect-triggered refetch, not a true push within 2s —
 * logged as BLOCKER in docs/DECISIONS.md rather than silently skipped.
 */
const CLINIC_ID = "00000000-0000-0000-0000-000000000001";
const PATIENT_ID = "00000000-0000-0000-0000-000000000101";
const DOCTOR_ID = "00000000-0000-0000-0000-000000000201";

async function createWalkIn(page: Page): Promise<string> {
  const res = await page.request.post("/api/v1/queue/walk-in", {
    data: { clinic_id: CLINIC_ID, patient_id: PATIENT_ID, doctor_id: DOCTOR_ID, severity_esi: 4 },
  });
  const body = (await res.json()) as { id: string };
  return body.id;
}

test.describe("queue", () => {
  test("escalating a patient reorders the board", async ({ page }) => {
    await loginAsDoctor(page);
    await page.waitForURL(/\/doctor/);

    const entryId = await createWalkIn(page);

    await page.goto("/doctor/queue");
    await expect(page.getByText(/live queue/i)).toBeVisible({ timeout: 5_000 });

    await page.request.post(`/api/v1/queue/${entryId}/escalate`, { data: { reason: "chest pain reported" } });

    await expect(page.getByText(/emergency/i)).toBeVisible({ timeout: 2_000 });
  });

  test("reconnects and resyncs without duplicate rows after a socket drop", async ({ page }) => {
    await loginAsDoctor(page);
    await page.waitForURL(/\/doctor/);
    await createWalkIn(page);

    await page.goto("/doctor/queue");
    await expect(page.getByText(/live queue/i)).toBeVisible({ timeout: 5_000 });

    await page.evaluate(() => window.dispatchEvent(new Event("offline")));
    await expect(page.getByText(/reconnecting/i)).toBeVisible({ timeout: 5_000 });

    await page.reload();
    const rows = page.locator("tbody tr");
    const ids = await rows.evaluateAll((els) => els.map((el) => el.textContent));
    expect(new Set(ids).size).toBe(ids.length);
  });
});
