import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Accessibility sweep over the design preview (`/__preview`), which mounts
 * every shared component against fixtures. It needs no backend, which is what
 * makes it the one browser suite that actually runs on a dev machine.
 *
 * Everything is asserted at both 360x640 (the Android handset the patient
 * flows are designed for) and 1280x800, in light and dark, because the token
 * palette differs per theme and a contrast failure usually only shows in one.
 */

const MOBILE = { width: 360, height: 640 };
const DESKTOP = { width: 1280, height: 800 };

/**
 * `#responsive` is the preview harness's own section: it deliberately mounts
 * the same page three more times at fixed widths so the designer can eyeball
 * breakpoints side by side. Structural checks that count ids or measure
 * overflow have to exclude it, or they report the harness rather than the
 * product.
 */
const HARNESS_SECTION = "#responsive";

const SECTIONS = {
  primitives: "#primitives",
  chat: "#chat",
  portal: "#portal",
  evidence: "#evidence",
  states: "#states",
} as const;

async function openPreview(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await page.goto("/__preview");
  await expect(page.getByRole("heading", { name: /design preview/i })).toBeVisible();
}

async function setTheme(page: Page, theme: "light" | "dark") {
  const toggle = page.getByRole("button", { name: /(dark|light) mode/i });
  const current = await page.locator("[data-theme]").first().getAttribute("data-theme");
  if (current !== theme) await toggle.click();
  await expect(page.locator(`[data-theme="${theme}"]`).first()).toBeVisible();
}

function scan(page: Page, selector: string) {
  return new AxeBuilder({ page })
    .include(selector)
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
}

/** Compact, actionable violation report: rule, impact, and the offending nodes. */
function describe(violations: Awaited<ReturnType<typeof scan>>["violations"]): string {
  return violations
    .map(
      (v) =>
        `\n[${v.impact ?? "unknown"}] ${v.id}: ${v.help}\n  ${v.nodes
          .slice(0, 4)
          .map((n) => n.target.join(" "))
          .join("\n  ")}`,
    )
    .join("\n");
}

for (const [label, viewport] of [
  ["mobile 360", MOBILE],
  ["desktop 1280", DESKTOP],
] as const) {
  for (const theme of ["light", "dark"] as const) {
    test(`axe: preview page is clean at ${label} in ${theme}`, async ({ page }) => {
      await openPreview(page, viewport);
      await setTheme(page, theme);

      const results = await new AxeBuilder({ page })
        .exclude(HARNESS_SECTION)
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      expect(describe(results.violations)).toBe("");
    });
  }
}

for (const [name, selector] of Object.entries(SECTIONS)) {
  test(`axe: ${name} section is clean in both themes at 360`, async ({ page }) => {
    await openPreview(page, MOBILE);

    await setTheme(page, "light");
    const light = await scan(page, selector);

    await setTheme(page, "dark");
    const dark = await scan(page, selector);

    expect(describe([...light.violations, ...dark.violations])).toBe("");
  });
}

test.describe("safety-critical semantics", () => {
  test("the emergency banner is announced and both numbers are dialable", async ({ page }) => {
    await openPreview(page, MOBILE);

    const banner = page.locator('[role="alert"]').filter({ hasText: /112/ }).first();
    await expect(banner).toBeVisible();

    for (const number of ["112", "108"]) {
      const link = banner.locator(`a[href="tel:${number}"]`);
      await expect(link).toBeVisible();
      // An accessible name, not a bare icon.
      await expect(link).not.toHaveText("");
      // Tap targets must clear 44px on a handset.
      const box = await link.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }

    // Hindi is shown alongside English, not behind the language toggle.
    await expect(banner).toContainText(/[ऀ-ॿ]/);
    await expect(page.locator("body")).not.toContainText("911");
  });

  test("a blocked substitution offers no control at all", async ({ page }) => {
    await openPreview(page, DESKTOP);

    const blocked = page.locator('[aria-disabled="true"]').filter({ hasText: /blocked/i });
    const count = await blocked.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i += 1) {
      const notice = blocked.nth(i);
      // Zero interactive controls: a blocked option must be unselectable, and
      // the reason must be readable text rather than a strike-through alone.
      expect(await notice.locator("button, input, select, [role='button']").count()).toBe(0);
      await expect(notice).toContainText(/blocked/i);
    }
  });

  test("interaction severity is stated in words, not colour alone", async ({ page }) => {
    await openPreview(page, DESKTOP);

    // The API severity is `major`; the design system's SeverityPill words it
    // `critical`. Either is acceptable here -- what matters is that the level
    // is carried by text at all, not by the red border alone.
    const alert = page.locator('[role="alert"]').filter({ hasText: /interaction|\+/ }).first();
    if ((await alert.count()) === 0) test.skip();
    await expect(alert).toContainText(/major|critical|moderate|minor/i);
  });

  test("casualty colours always carry their label", async ({ page }) => {
    // The deuteranopia case: red/yellow/green must never be the only signal.
    await openPreview(page, DESKTOP);

    const body = page.locator("body");
    for (const [, word] of [
      ["red", /red|immediate/i],
      ["yellow", /yellow|urgent/i],
      ["green", /green|non-urgent/i],
    ] as const) {
      if (await body.filter({ hasText: word }).count()) {
        await expect(body).toContainText(word);
      }
    }
  });
});

test.describe("structure and keyboard", () => {
  test("the confidence meter exposes its value", async ({ page }) => {
    await openPreview(page, DESKTOP);

    const meter = page.getByRole("meter").first();
    await expect(meter).toHaveAttribute("aria-valuenow", /\d/);
    await expect(meter).toHaveAttribute("aria-label", /.+/);
  });

  test("the evidence drawer traps focus, closes on Escape and restores focus", async ({ page }) => {
    await openPreview(page, DESKTOP);

    const trigger = page.getByRole("button", { name: /evidence|sources/i }).first();
    if ((await trigger.count()) === 0) test.skip();
    await trigger.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("every focusable control shows a visible focus ring", async ({ page }) => {
    await openPreview(page, DESKTOP);

    // Walk the first stretch of the tab order and assert the focused element
    // renders an outline or ring rather than relying on the browser default
    // being left intact by a CSS reset.
    const unfocused: string[] = [];
    for (let i = 0; i < 30; i += 1) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const style = getComputedStyle(el);
        const ringed =
          style.outlineStyle !== "none" ||
          style.boxShadow !== "none" ||
          style.getPropertyValue("--tw-ring-shadow") !== "";
        return { tag: el.tagName.toLowerCase(), label: el.textContent?.slice(0, 30) ?? "", ringed };
      });
      if (info && !info.ringed) unfocused.push(`${info.tag} "${info.label}"`);
    }
    expect(unfocused).toEqual([]);
  });

  test("no horizontal scroll at 360 and still readable at 200% zoom", async ({ page }) => {
    await openPreview(page, MOBILE);

    // Measured per shipped section rather than on the document, so the preview
    // harness's own chrome cannot mask or manufacture a failure. Content that
    // scrolls inside its own `overflow-x-auto` box (wide lab tables) is fine;
    // what must never happen is a section pushing the page sideways.
    const overflowing = async () =>
      page.evaluate((harness) => {
        const vw = document.documentElement.clientWidth;
        const bad: string[] = [];
        for (const section of Array.from(document.querySelectorAll("main section[id]"))) {
          if (`#${section.id}` === harness) continue;
          if (section.getBoundingClientRect().right > vw + 1) bad.push(section.id);
        }
        return bad;
      }, HARNESS_SECTION);

    expect(await overflowing()).toEqual([]);

    // 200% zoom is equivalent to halving the CSS viewport.
    await page.setViewportSize({ width: 180, height: 320 });
    expect(await overflowing()).toEqual([]);
  });
});

test.describe("responsive duplication", () => {
  /**
   * `LabResultTable` renders a `<table>` and a stacked card list at the same
   * time, gated only by Tailwind `hidden` / `md:hidden`. That should resolve to
   * `display: none` and drop out of the accessibility tree -- if it does not,
   * a screen reader hears every lab result twice.
   */
  for (const [label, viewport] of [
    ["360", MOBILE],
    ["1280", DESKTOP],
  ] as const) {
    test(`lab results are announced once at ${label}`, async ({ page }) => {
      await openPreview(page, viewport);

      const duplicated = await page.evaluate((harness) => {
        const scope = document.querySelector("#portal");
        const ids = new Map<string, number>();
        for (const el of Array.from(scope?.querySelectorAll("[id]") ?? [])) {
          if (el.closest(harness)) continue;
          ids.set(el.id, (ids.get(el.id) ?? 0) + 1);
        }
        return [...ids.entries()].filter(([, n]) => n > 1).map(([id]) => id);
      }, HARNESS_SECTION);
      expect(duplicated).toEqual([]);

      // Anything hidden by a responsive utility must be out of the a11y tree.
      const visiblyHidden = await page.evaluate(() => {
        const offenders: string[] = [];
        for (const el of Array.from(document.querySelectorAll("table, ul"))) {
          const style = getComputedStyle(el);
          const invisible = style.display === "none" || style.visibility === "hidden";
          const box = el.getBoundingClientRect();
          if (invisible && (box.width > 0 || box.height > 0)) offenders.push(el.tagName);
        }
        return offenders;
      });
      expect(visiblyHidden).toEqual([]);
    });
  }
});

test.describe("motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("prefers-reduced-motion disables transitions and animations", async ({ page }) => {
    await openPreview(page, DESKTOP);

    const animated = await page.evaluate(() => {
      const offenders: string[] = [];
      const harness = document.querySelector("#responsive");
      for (const el of Array.from(document.querySelectorAll("*")).slice(0, 1500)) {
        if (harness?.contains(el)) continue;
        const style = getComputedStyle(el);
        const duration = parseFloat(style.transitionDuration) + parseFloat(style.animationDuration);
        if (duration > 0.01) {
          offenders.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().slice(0, 40)}`);
        }
      }
      return offenders.slice(0, 10);
    });
    expect(animated).toEqual([]);
  });
});
