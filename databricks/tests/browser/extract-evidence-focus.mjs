import assert from "node:assert/strict";
import { chromium, firefox, expect } from "@playwright/test";
const results = [];
for (const [name, engine, executablePath] of [
  ["chromium", chromium, process.env.EVIDENCE_CHROMIUM],
  ["firefox", firefox, process.env.EVIDENCE_FIREFOX],
]) {
  const browser = await engine.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.setDefaultTimeout(15000);
  let check = "ordinary visibility";
  let pdfZoom;
  try {
    const entry = process.env.EVIDENCE_TEST_URL;
    await page.goto(entry);
    await page.getByText("Document A", { exact: true }).waitFor();
    const labels = page.locator("[data-annotation-label]");
    await labels.first().waitFor({ state: "attached" });
    const highlights = page.locator(
      '[data-testid="pdf-pane"] [id^="SELECTION_"]:not([id^="SELECTION_TOKEN_"])'
    );
    await expect(highlights).toHaveCount(2, { timeout: 15000 });
    assert.equal(
      await labels.first().isVisible(),
      false,
      `${name}: ordinary labels start hidden`
    );
    await page
      .getByRole("button", { name: "2 Annotations", exact: true })
      .click();
    const cards = page.locator(
      '[data-testid="extract-pane"] [data-annotation-id]'
    );
    await cards.first().click();
    await page.mouse.move(1400, 30);
    const firstId = await cards.first().getAttribute("data-annotation-id");
    const firstLabel = page.locator(`[data-annotation-label="${firstId}"]`);
    await firstLabel.waitFor({ state: "visible" });
    check = "source toggle";
    await cards.first().click();
    await firstLabel.waitFor({ state: "hidden" });
    await cards.last().click();
    const highlight = page.locator(`[id="SELECTION_${firstId}"]`);
    check = "plain hover";
    await highlight.hover(); // Plain pointer movement, without Shift or internal events.
    await firstLabel.waitFor({ state: "visible" });
    const control = firstLabel.locator(".pulsing-dot");
    check = "label-control transfer";
    await control.hover();
    const action = firstLabel.getByRole("button", {
      name: "Login to see available actions!",
      exact: true,
    });
    await action.waitFor({ state: "visible" });
    page.on("dialog", (dialog) => dialog.dismiss());
    check = "native label action";
    await action.click();
    check = "leave unfocused label";
    await page.mouse.move(1400, 30);
    await firstLabel.waitFor({ state: "hidden" });
    await cards.first().click();
    await page.mouse.move(1400, 30);
    await firstLabel.waitFor({ state: "visible" });
    await page.waitForTimeout(1000);
    const pane = page.locator('[data-testid="pdf-pane"]');
    check = "pane retention";
    pdfZoom = await page.getByLabel("Zoom", { exact: true }).textContent();
    const before = await pane.evaluate((element) => element.scrollTop);
    await page
      .getByRole("button", { name: "Toggle Extract pane", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Resize Extract pane", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Toggle Extract pane", exact: true })
      .click();
    await page.waitForTimeout(1000);
    const after = await pane.evaluate((element) => element.scrollTop);
    assert.ok(
      Math.abs(after - before) <= 1,
      `${name}: pane changes retain PDF position within a rendered pixel (${before} → ${after})`
    );
    assert.equal(
      await firstLabel.isVisible(),
      true,
      `${name}: pane reopening retains evidence focus`
    );
    await page
      .getByRole("button", { name: "2 Annotations", exact: true })
      .click();
    assert.equal(await cards.first().getAttribute("aria-current"), "true");
    check = "Hide and Always";
    await page
      .getByRole("button", { name: "HIDE labels", exact: true })
      .click();
    await firstLabel.waitFor({ state: "hidden" });
    await expect(highlights).toHaveCount(2, { timeout: 15000 });
    await page
      .getByRole("button", { name: "ALWAYS labels", exact: true })
      .click();
    await labels.first().waitFor({ state: "visible" });
    await labels.last().waitFor({ state: "visible" });
    check = "warm SPA exit and ordinary same-document return";
    await page
      .getByRole("button", { name: "Default labels", exact: true })
      .click();
    await firstLabel.waitFor({ state: "visible" });
    await page
      .getByRole("button", { name: "Open extract grid", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open Document A", exact: true })
      .waitFor();
    assert.equal(await page.locator('[data-testid="pdf-pane"]').count(), 0);
    await page
      .getByRole("button", { name: "Open Document A", exact: true })
      .click();
    await page.getByText("Document A", { exact: true }).waitFor();
    await labels.first().waitFor({ state: "attached" });
    await firstLabel.waitFor({ state: "hidden" });
    assert.equal(new URL(page.url()).searchParams.get("ann"), null);
    await expect(highlights).toHaveCount(2, { timeout: 15000 });
    await page
      .getByRole("button", { name: "2 Annotations", exact: true })
      .click();
    assert.equal(
      await page
        .locator('[data-testid="extract-pane"] [aria-current="true"]')
        .count(),
      0
    );
    check = "ordinary document exit";
    await page
      .getByRole("button", { name: "Default labels", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open other document", exact: true })
      .click();
    await page.getByText("Document B", { exact: true }).waitFor();
    await labels.first().waitFor({ state: "attached" });
    assert.equal(
      await labels.first().isVisible(),
      false,
      `${name}: ordinary document change clears focus`
    );
    assert.equal(
      await page.locator(`[data-annotation-label="${firstId}"]`).count(),
      0
    );
    check = "direct evidence entry and URL mode reload";
    for (const mode of [null, "ON_HOVER", "HIDE", "ALWAYS"]) {
      const url = new URL(entry);
      url.searchParams.set("target", "1");
      if (mode) url.searchParams.set("labels", mode);
      await page.goto(url.toString());
      for (const reload of [false, true]) {
        if (reload) await page.reload();
        await page.getByText("Document A", { exact: true }).waitFor();
        await labels.first().waitFor({ state: "attached" });
        await page.waitForTimeout(200);
        assert.equal(new URL(page.url()).searchParams.get("labels"), mode);
        assert.equal(
          await page
            .locator(`[data-annotation-label="${firstId}"]`)
            .isVisible(),
          mode !== "HIDE",
          `${name}: first evidence target visible in ${
            mode ?? "default"
          }, reload=${reload}`
        );
        assert.equal(
          await labels.last().isVisible(),
          mode === "ALWAYS",
          `${name}: unrelated label visibility in ${
            mode ?? "default"
          }, reload=${reload}`
        );
        await expect(highlights).toHaveCount(2, { timeout: 15000 });
      }
    }
    results.push({
      browser: name,
      version: browser.version(),
      pdfZoom,
      ok: true,
      viewport: "1440x1000",
      checks: [
        "ordinary visibility",
        "source focus/toggle",
        "plain hover",
        "label-control pointer transfer",
        "pane focus/scroll retention",
        "Hide/Always",
        "warm SPA same-document return",
        "ordinary document exit",
        "direct-link entry/reload modes",
      ],
    });
  } catch (error) {
    results.push({ browser: name, ok: false, check, error: String(error) });
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify(results));
if (results.some((result) => !result.ok)) process.exitCode = 1;
