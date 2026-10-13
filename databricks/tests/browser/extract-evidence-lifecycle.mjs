import assert from "node:assert/strict";
import { chromium, firefox, expect } from "@playwright/test";

const results = [];
for (const [name, engine, executablePath] of [
  ["chromium", chromium, process.env.EVIDENCE_CHROMIUM],
  ["firefox", firefox, process.env.EVIDENCE_FIREFOX],
]) {
  const browser = await engine.launch({ headless: true, executablePath });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.setDefaultTimeout(15000);
  let check = "source entry and multipage focus";
  try {
    await page.goto(process.env.EVIDENCE_TEST_URL);
    await page.getByText("Document A", { exact: true }).waitFor();
    const firstId = Buffer.from("AnnotationType:11").toString("base64");
    const pane = page.getByTestId("pdf-pane");
    const labels = pane.locator(`[data-annotation-label="${firstId}"]`);
    await expect(labels).toHaveCount(2);
    await expect(labels.nth(0)).toBeVisible();
    await expect(labels.nth(1)).toBeVisible();
    // Native source entry keeps plural selection. Move to its second occurrence
    // with a real wheel, then let the native sidebar auto-zoom change layout.
    await page.waitForTimeout(1000);
    await pane.hover({ position: { x: 450, y: 400 } });
    for (let move = 0; move < 4; move++) {
      const y = (await labels.nth(1).boundingBox()).y;
      if (y < 700) break;
      await page.mouse.wheel(0, y - 400);
      await page.waitForTimeout(350);
    }
    await expect
      .poll(async () => (await labels.nth(1).boundingBox()).y)
      .toBeLessThan(700);
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(500);
    check = "pane auto-zoom preserves manually inspected page";
    const beforeZoom = Number(
      await page.getByLabel("Zoom", { exact: true }).textContent()
    );
    await page
      .getByRole("button", { name: "Toggle Extract pane", exact: true })
      .click();
    await expect
      .poll(async () =>
        Number(await page.getByLabel("Zoom", { exact: true }).textContent())
      )
      .toBeGreaterThan(beforeZoom);
    await page.waitForTimeout(1200);
    const box = await labels.nth(1).boundingBox();
    const viewport = await pane.boundingBox();
    assert.ok(
      box.y >= viewport.y && box.y < viewport.y + viewport.height,
      `${name}: manually inspected page2 label remains in viewport after pane auto-zoom (${box.y})`
    );
    const checks = [check];
    check = "repeated zoom and pane return retain page-local focus";
    await page
      .getByRole("button", { name: "Toggle Extract pane", exact: true })
      .click();
    await page.waitForTimeout(800);
    for (const key of ["Control+=", "Control+-", "Control+=", "Control+-"]) {
      await page.keyboard.press(key);
      await page.waitForTimeout(250);
      const target = await labels.nth(1).boundingBox();
      const view = await pane.boundingBox();
      assert.ok(
        target.y >= view.y && target.y < view.y + view.height,
        `${name}: ${key} preserves page2 reading position`
      );
    }
    await expect(labels.nth(0)).toBeVisible();
    await expect(labels.nth(1)).toBeVisible();
    const pages = pane.locator(".PageAnnotationsContainer");
    await expect(pages).toHaveCount(3);
    await expect(
      pages.nth(2).locator(`[data-annotation-label="${firstId}"]`)
    ).toHaveCount(0);
    checks.push(check);
    check = "visible page without focused geometry shows no leaked label";
    await pane.hover({ position: { x: 450, y: 400 } });
    for (let move = 0; move < 5; move++) {
      const y = (await pages.nth(2).boundingBox()).y;
      const view = await pane.boundingBox();
      if (y < view.y + 300) break;
      await page.mouse.wheel(0, y - view.y - 100);
      await page.waitForTimeout(350);
    }
    await expect
      .poll(async () => (await pages.nth(2).boundingBox()).y)
      .toBeLessThan((await pane.boundingBox()).y + 300);
    await expect(
      pages.nth(2).locator(`[id="SELECTION_${firstId}"]`)
    ).toHaveCount(0);
    await expect(
      pages.nth(2).locator(`[data-annotation-label="${firstId}"]`)
    ).toHaveCount(0);
    await page.mouse.move(1400, 30);
    checks.push(check);
    check =
      "new explicit source inspection still navigates after manual scroll and zoom";
    await page
      .getByRole("button", { name: "3 Annotations", exact: true })
      .click();
    const firstCard = page
      .getByTestId("extract-pane")
      .locator(`[data-annotation-id="${firstId}"]`);
    await firstCard.click();
    await expect(firstCard).not.toHaveAttribute("aria-current", "true");
    await firstCard.click();
    await expect(firstCard).toHaveAttribute("aria-current", "true");
    await page.mouse.move(1400, 30);
    await expect
      .poll(async () => (await labels.nth(0).boundingBox()).y)
      .toBeGreaterThan((await pane.boundingBox()).y);
    await expect
      .poll(async () => (await labels.nth(0).boundingBox()).y)
      .toBeLessThan((await pane.boundingBox()).y + 760);
    checks.push(check);
    check = "native label exclusions restore remembered focus under all modes";
    const secondId = Buffer.from("AnnotationType:12").toString("base64");
    const selector = page.getByRole("region", { name: "Native label filter" });
    for (const mode of ["Default", "ALWAYS", "HIDE"]) {
      await page
        .getByRole("button", { name: `${mode} labels`, exact: true })
        .click();
      await selector.getByRole("combobox").click();
      await page
        .getByRole("option", { name: "Document A second quote", exact: true })
        .click();
      await page.mouse.move(1400, 30);
      await expect(pane.locator(`[id="SELECTION_${firstId}"]`)).toHaveCount(0);
      await expect(
        pane.locator(`[data-annotation-label="${firstId}"]`)
      ).toHaveCount(0);
      await expect(firstCard).toHaveAttribute("aria-current", "true");
      await expect(pane.locator(`[id="SELECTION_${secondId}"]`)).toHaveCount(1);
      await page
        .getByRole("option", { name: "Document A second quote", exact: true })
        .click();
      await page.getByText("Document A", { exact: true }).click();
      await expect(labels).toHaveCount(2);
      await expect(firstCard).toHaveAttribute("aria-current", "true");
      if (mode === "HIDE") await expect(labels.nth(0)).toBeHidden();
      else await expect(labels.nth(0)).toBeVisible();
      if (mode === "ALWAYS")
        await expect(
          pane.locator(`[data-annotation-label="${secondId}"]`)
        ).toBeVisible();
      else
        await expect(
          pane.locator(`[data-annotation-label="${secondId}"]`)
        ).toBeHidden();
    }
    checks.push(check);
    check =
      "selected-only exclusions remember singular focus without changing selection membership";
    for (const mode of ["ON_HOVER", "ALWAYS", "HIDE"]) {
      const entry = new URL(process.env.EVIDENCE_TEST_URL);
      entry.searchParams.delete("target");
      entry.searchParams.set("ann", firstId);
      entry.searchParams.set("labels", mode);
      await page.goto(entry.toString());
      await expect(labels).toHaveCount(2);
      await page
        .getByRole("button", { name: "3 Annotations", exact: true })
        .click();
      const secondCard = page
        .getByTestId("extract-pane")
        .locator(`[data-annotation-id="${secondId}"]`);
      await secondCard.click();
      await expect(secondCard).toHaveAttribute("aria-current", "true");
      await page
        .getByRole("button", { name: "Show selected only", exact: true })
        .click();
      await expect(pane.locator('[id^="SELECTION_"]')).toHaveCount(1);
      await expect(pane.locator(`[id="SELECTION_${secondId}"]`)).toHaveCount(1);
      await expect(pane.locator(`[id="SELECTION_${firstId}"]`)).toHaveCount(0);
      await expect(secondCard).toHaveAttribute("aria-current", "true");
      const selectedUrl = new URL(page.url()).searchParams.get("ann");
      assert.equal(
        selectedUrl,
        secondId,
        "source navigation preserves the native viewer selection destination"
      );
      await secondCard.click();
      await expect(secondCard).not.toHaveAttribute("aria-current", "true");
      await expect(pane.locator('[id^="SELECTION_"]')).toHaveCount(1);
      await expect(pane.locator("[data-annotation-label]:visible")).toHaveCount(
        mode === "ALWAYS" ? 1 : 0
      );
      assert.equal(
        new URL(page.url()).searchParams.get("ann"),
        selectedUrl,
        "clearing singular focus does not change selection membership"
      );
      await secondCard.click();
      await expect(secondCard).toHaveAttribute("aria-current", "true");
      await expect(pane.locator('[id^="SELECTION_"]')).toHaveCount(1);
      assert.equal(
        new URL(page.url()).searchParams.get("ann"),
        selectedUrl,
        "restoring singular focus does not change selection membership"
      );
      // The public display action restores all eligible highlights. Native mode
      // actions then respect the remembered second source instead of selecting it.
      await page
        .getByRole("button", { name: "Default labels", exact: true })
        .click();
      if (mode !== "ON_HOVER")
        await page
          .getByRole("button", { name: `${mode} labels`, exact: true })
          .click();
      await page.mouse.move(1400, 30);
      await expect(pane.locator('[id^="SELECTION_"]')).toHaveCount(4);
      await expect(secondCard).toHaveAttribute("aria-current", "true");
      if (mode === "HIDE")
        await expect(
          pane.locator(`[data-annotation-label="${secondId}"]`)
        ).toBeHidden();
      else
        await expect(
          pane.locator(`[data-annotation-label="${secondId}"]`)
        ).toBeVisible();
      await expect(pane.locator("[data-annotation-label]:visible")).toHaveCount(
        mode === "ALWAYS" ? 4 : mode === "HIDE" ? 0 : 1
      );
    }
    checks.push(check);
    check =
      "selected-only multi-target inspection retains all existing members";
    await page.goto(process.env.EVIDENCE_TEST_URL);
    await expect(labels).toHaveCount(2);
    await page
      .getByRole("button", { name: "3 Annotations", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Show selected only", exact: true })
      .click();
    await expect(pane.locator('[id^="SELECTION_"]')).toHaveCount(3);
    const membersUrl = new URL(page.url()).searchParams.get("ann");
    const firstMember = page
      .getByTestId("extract-pane")
      .locator(`[data-annotation-id="${firstId}"]`);
    await firstMember.click();
    await firstMember.click();
    await page
      .getByTestId("extract-pane")
      .locator(`[data-annotation-id="${secondId}"]`)
      .click();
    await expect(pane.locator('[id^="SELECTION_"]')).toHaveCount(3);
    await expect(pane.locator("[data-annotation-label]:visible")).toHaveCount(
      1
    );
    assert.equal(new URL(page.url()).searchParams.get("ann"), membersUrl);
    assert.equal(new URL(page.url()).searchParams.get("selectedOnly"), "true");
    checks.push(check);
    check =
      "native source-version picker clears prior source focus and preserves explicit label mode";
    for (const mode of ["ON_HOVER", "ALWAYS", "HIDE"]) {
      const entry = new URL(process.env.EVIDENCE_TEST_URL);
      entry.searchParams.set("labels", mode);
      await page.goto(entry.toString());
      await expect(labels).toHaveCount(2);
      await page
        .getByRole("button", {
          name: "Version 2 of 2, click to switch versions",
          exact: true,
        })
        .click();
      await page.getByRole("option", { name: /^Version 1/ }).click();
      await page.getByText("Document A historical", { exact: true }).waitFor();
      await expect(labels).toHaveCount(0);
      const historicalId = Buffer.from("AnnotationType:15").toString("base64");
      const historical = pane.locator(
        `[data-annotation-label="${historicalId}"]`
      );
      await expect(historical).toHaveCount(1);
      if (mode === "ALWAYS") await expect(historical).toBeVisible();
      else await expect(historical).toBeHidden();
      assert.equal(new URL(page.url()).searchParams.get("labels"), mode);
      assert.equal(new URL(page.url()).searchParams.get("v"), "1");
      await page.reload();
      await page.getByText("Document A historical", { exact: true }).waitFor();
      await expect(historical).toHaveCount(1);
      if (mode === "ALWAYS") await expect(historical).toBeVisible();
      else await expect(historical).toBeHidden();
      assert.equal(new URL(page.url()).searchParams.get("labels"), mode);
      assert.equal(new URL(page.url()).searchParams.get("v"), "1");
      await page
        .getByRole("button", { name: "2 Annotations", exact: true })
        .click();
      await expect(
        page.getByTestId("extract-pane").locator('[aria-current="true"]')
      ).toHaveCount(0);
      await page
        .getByRole("button", {
          name: "Version 1 of 2, click to switch versions",
          exact: true,
        })
        .click();
      await page.getByRole("option", { name: /^Version 2/ }).click();
      await page.getByText("Document A", { exact: true }).waitFor();
      await expect(labels).toHaveCount(2);
      if (mode === "HIDE") await expect(labels.nth(0)).toBeHidden();
      else await expect(labels.nth(0)).toBeVisible();
      assert.equal(new URL(page.url()).searchParams.get("v"), null);
      assert.equal(new URL(page.url()).searchParams.get("labels"), mode);
      // Returning latest legitimately resolves its retained explicit evidence
      // link. A warm ordinary return without that target starts unfocused.
      await page
        .getByRole("button", { name: "Default labels", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Open extract grid", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Open Document A", exact: true })
        .click();
      await page.getByText("Document A", { exact: true }).waitFor();
      await expect(labels).toHaveCount(2);
      await expect(pane.locator("[data-annotation-label]:visible")).toHaveCount(
        0
      );
      assert.equal(new URL(page.url()).searchParams.get("ann"), null);
    }
    checks.push(check);
    results.push({
      browser: name,
      version: browser.version(),
      ok: true,
      checks,
    });
  } catch (error) {
    results.push({ browser: name, ok: false, check, error: String(error),
      versionControls: await page.locator('button[aria-label^="Version "]').evaluateAll(elements => elements.map(element => element.getAttribute("aria-label"))),
      search: new URL(page.url()).search,
    });
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify(results));
if (results.some((result) => !result.ok)) process.exitCode = 1;
