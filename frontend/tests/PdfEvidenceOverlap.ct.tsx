import React from "react";
import { test, expect } from "./utils/coverage";
import { PdfEvidenceOverlapTestWrapper } from "./PdfEvidenceOverlapTestWrapper";

test.describe("PDF evidence pointer and focus integration", () => {
  for (const scale of [0.5, 1, 2]) {
    test(`cycles exact repeated-quotation associations at scale${scale} after hover reveals controls`, async ({
      mount,
      page,
    }) => {
      await mount(<PdfEvidenceOverlapTestWrapper scale={scale} />);
      const boxes = await page
        .locator("[data-pdf-evidence-target]")
        .evaluateAll((elements) =>
          elements.map((element) => {
            const r = element.getBoundingClientRect();
            return {
              left: r.left,
              right: r.right,
              top: r.top,
              bottom: r.bottom,
            };
          })
        );
      const x =
        (Math.max(...boxes.map((b) => b.left)) +
          Math.min(...boxes.map((b) => b.right))) /
        2;
      const y =
        (Math.max(...boxes.map((b) => b.top)) +
          Math.min(...boxes.map((b) => b.bottom))) /
        2;
      await page.mouse.move(x, y);
      await page.waitForTimeout(300);
      for (const id of ["evidence-a", "evidence-b", "evidence-a"]) {
        await page.mouse.click(x, y);
        await expect(page.getByLabel("Focused evidence")).toHaveText(id);
      }
    });
  }

  test("persistent active appearance moves with inspection and clears with document context", async ({
    mount,
    page,
  }) => {
    await mount(<PdfEvidenceOverlapTestWrapper />);
    const a = page.locator('[data-pdf-evidence-target="evidence-a"]');
    const b = page.locator('[data-pdf-evidence-target="evidence-b"]');
    const inactive = await a.evaluate(
      (element) => getComputedStyle(element).backgroundColor
    );
    await page.getByRole("button", { name: "Inspect source A" }).click();
    await page.mouse.move(5, 5);
    await expect
      .poll(() =>
        a.evaluate((element) => getComputedStyle(element).backgroundColor)
      )
      .not.toBe(inactive);
    await page.getByRole("button", { name: "Inspect source B" }).click();
    await expect
      .poll(() =>
        b.evaluate((element) => getComputedStyle(element).backgroundColor)
      )
      .not.toBe(inactive);
    await expect
      .poll(() =>
        a.evaluate((element) => getComputedStyle(element).backgroundColor)
      )
      .toBe(inactive);
    await page.getByRole("button", { name: "Switch document" }).click();
    await expect(page.getByLabel("Focused evidence")).toHaveText("None");
    await expect
      .poll(() =>
        b.evaluate((element) => getComputedStyle(element).backgroundColor)
      )
      .toBe(inactive);
  });

  test("keyboard evidence inspection and annotation actions remain independent", async ({
    mount,
    page,
  }) => {
    await mount(<PdfEvidenceOverlapTestWrapper />);
    await page.getByRole("button", { name: "Switch document" }).focus();
    await page.keyboard.press("Tab");
    await expect(
      page.locator('[data-pdf-evidence-target="evidence-a"]')
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Focused evidence")).toHaveText("evidence-a");
    const launcher = page
      .getByRole("button", { name: "Annotation actions" })
      .first();
    await launcher.focus();
    await page.keyboard.press("Enter");
    await expect(launcher).toHaveAttribute("aria-expanded", "true");
    const action = page.getByTitle("Login to see available actions!").first();
    await expect(action).toBeVisible();
    const alert = page
      .waitForEvent("dialog")
      .then((dialog) => dialog.dismiss());
    await action.click();
    await alert;
    await launcher.focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Escape");
    await expect(launcher).toHaveAttribute("aria-expanded", "false");
    await expect(launcher).toBeFocused();
    await expect(page.getByLabel("Focused evidence")).toHaveText("evidence-a");
  });
});
