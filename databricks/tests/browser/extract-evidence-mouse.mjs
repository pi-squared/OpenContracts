import assert from "node:assert/strict";
import { chromium, firefox, expect } from "@playwright/test";
const results = [];
for (const [name, engine, executablePath] of [
  ["chromium", chromium, process.env.EVIDENCE_CHROMIUM],
  ["firefox", firefox, process.env.EVIDENCE_FIREFOX],
]) {
  const browser = await engine.launch({
    headless: true,
    ...(name === "firefox"
      ? { firefoxUserPrefs: { "dom.events.testing.asyncClipboard": true } }
      : {}),
    ...(executablePath ? { executablePath } : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.setDefaultTimeout(15000);
  let check = "ordinary mouse fixture";
  let denseControlObservation;
  let urlDialogObservation;
  try {
    const entry = process.env.EVIDENCE_TEST_URL;
    const pane = page.locator('[data-testid="pdf-pane"]');
    const settlePages = async () => {
      await expect
        .poll(
          async () =>
            (await pane.locator("canvas").first().boundingBox())?.height ?? 0
        )
        .toBeGreaterThan(1200);
      await expect
        .poll(() =>
          pane.locator("canvas").evaluateAll((elements) => {
            const boxes = elements.map((element) =>
              element.getBoundingClientRect()
            );
            return boxes.every(
              (box, index) => !index || box.top >= boxes[index - 1].bottom
            );
          })
        )
        .toBe(true);
    };
    const highlights = pane.locator(
      '[id^="SELECTION_"]:not([id^="SELECTION_TOKEN_"])'
    );
    check = "native fullscreen PDF full-overlap cycle";
    const mouseEntry = new URL(entry);
    mouseEntry.searchParams.set("mouse", "1");
    await page.goto(mouseEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await expect(page.locator("#knowledge-base-modal")).toHaveAttribute(
      "role",
      "dialog"
    );
    await expect(
      page.locator("#knowledge-base-modal").locator(pane)
    ).toBeVisible();
    await expect(highlights).toHaveCount(5);
    await settlePages();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    const mouseCards = page.locator(
      '[data-testid="extract-pane"] [data-annotation-id]'
    );
    const mouseIds = await mouseCards.evaluateAll((elements) =>
      elements.map((element) => element.getAttribute("data-annotation-id"))
    );
    const evidenceLabel = (index) =>
      page.locator(`[data-annotation-label="${mouseIds[index]}"]`);
    const sourceHighlight = page.locator(`[id="SELECTION_${mouseIds[0]}"]`);
    await sourceHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const box = await sourceHighlight.boundingBox();
    const fullPoint = { x: box.x + box.width / 6, y: box.y + box.height / 2 };
    const paneBeforeCycle = await pane.evaluate((element) => element.scrollTop);
    const zoomBeforeCycle = await page
      .getByLabel("Zoom", { exact: true })
      .textContent();
    for (const index of [0, 1, 3, 0]) {
      await page.mouse.click(fullPoint.x, fullPoint.y);
      await page.mouse.move(1400, 30);
      await evidenceLabel(index).waitFor({ state: "visible" });
      await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
        1
      );
      assert.equal(
        await mouseCards.nth(index).getAttribute("aria-current"),
        "true"
      );
      assert.equal(
        await pane.evaluate((element) => element.scrollTop),
        paneBeforeCycle
      );
      assert.equal(
        await page.getByLabel("Zoom", { exact: true }).textContent(),
        zoomBeforeCycle
      );
    }
    check = "partial overlap, out-of-set focus and no transitive candidates";
    const scale = box.width / 150;
    const partialPoint = { x: box.x + 180 * scale, y: fullPoint.y };
    const sharedPoint = { x: box.x + 120 * scale, y: fullPoint.y };
    const inspect = async (point, index) => {
      await page.mouse.click(point.x, point.y);
      await page.mouse.move(1400, 30);
      await evidenceLabel(index).waitFor({ state: "visible" });
      await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
        1
      );
      assert.equal(
        await mouseCards.nth(index).getAttribute("aria-current"),
        "true"
      );
    };
    await inspect(partialPoint, 2); // x230 is covered by C alone, not transitive E.
    await inspect(fullPoint, 0); // C is outside the A/B/D candidate set.
    for (const index of [1, 2, 3, 0]) await inspect(sharedPoint, index);
    await expect(highlights).toHaveCount(5);
    await settlePages();

    check = "shared hover readability and independent label controls";
    for (const index of [0, 1, 2, 3]) {
      check = `shared hover/readable control ${index}`;
      const transferScroll = await pane.evaluate(
        (element) => element.scrollTop
      );
      const currentBox = await sourceHighlight.boundingBox();
      await page.mouse.move(
        currentBox.x + currentBox.width * 0.8,
        currentBox.y + currentBox.height / 2
      );
      await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
        4
      );
      await expect(evidenceLabel(4)).toBeHidden();
      await expect
        .poll(async () =>
          page
            .locator("[data-annotation-label]:visible")
            .evaluateAll((elements) => {
              const boxes = elements.map((element) =>
                element.getBoundingClientRect()
              );
              return boxes.every(
                (a, i) =>
                  a.width > 20 &&
                  a.height > 10 &&
                  boxes.every(
                    (b, j) =>
                      i === j ||
                      a.right <= b.left ||
                      b.right <= a.left ||
                      a.bottom <= b.top ||
                      b.bottom <= a.top
                  )
              );
            })
        )
        .toBe(true);
      const control = evidenceLabel(index).locator(".pulsing-dot");
      const action = evidenceLabel(index).getByRole("button", {
        name: "Login to see available actions!",
        exact: true,
      });
      const labelText = evidenceLabel(index).locator("span").last();
      const textBox = await labelText.boundingBox();
      await page.mouse.move(
        textBox.x + textBox.width / 2,
        textBox.y + textBox.height / 2
      );
      // Entering the label can already pass through its enlarged native dot.
      // An open native cloud intentionally covers its own opener.
      if (!(await action.isVisible())) {
        await expect
          .poll(() =>
            control.evaluate((element) => {
              const rect = element.getBoundingClientRect();
              return element.contains(
                document.elementFromPoint(
                  rect.left + rect.width / 2,
                  rect.top + rect.height / 2
                )
              );
            })
          )
          .toBe(true);
        const controlBox = await control.boundingBox();
        await page.mouse.move(
          controlBox.x + controlBox.width / 2,
          controlBox.y + controlBox.height / 2
        );
      }
      await action.waitFor({ state: "visible" });
      await expect
        .poll(() =>
          action.evaluate((element) => getComputedStyle(element).opacity)
        )
        .toBe("1");
      await expect
        .poll(() =>
          action.evaluate((element) => {
            const rect = element.getBoundingClientRect();
            return element.contains(
              document.elementFromPoint(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2
              )
            );
          })
        )
        .toBe(true);
      const actionBox = await action.boundingBox();
      const controlScroll = await pane.evaluate((element) => element.scrollTop);
      assert.equal(controlScroll, transferScroll);
      await Promise.all([
        page.waitForEvent("dialog").then((dialog) => dialog.dismiss()),
        page.mouse.click(
          actionBox.x + actionBox.width / 2,
          actionBox.y + actionBox.height / 2
        ),
      ]);
      assert.equal(
        await pane.evaluate((element) => element.scrollTop),
        controlScroll
      );
      await page.mouse.move(1400, 30);
      await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
        1
      );
      assert.equal(
        await mouseCards.first().getAttribute("aria-current"),
        "true"
      );
    }

    check = "label exclusions restrict geometry candidates";
    await page
      .getByRole("button", { name: "Show only A and C labels", exact: true })
      .click();
    await expect(highlights).toHaveCount(2);
    await inspect(sharedPoint, 2);
    await inspect(sharedPoint, 0);
    await page
      .getByRole("button", { name: "Include all labels", exact: true })
      .click();
    await expect(highlights).toHaveCount(5);
    await settlePages();

    check = "pane finding membership stays independent of PDF focus";
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await page
      .getByRole("button", { name: "1 Annotation", exact: true })
      .click();
    await expect(mouseCards).toHaveCount(1);
    await page.mouse.click(fullPoint.x, fullPoint.y); // A -> B; shared finding contains only A.
    await page.mouse.move(1400, 30);
    await expect(mouseCards).toHaveCount(1);
    await expect(mouseCards.first()).not.toHaveAttribute(
      "aria-current",
      "true"
    );
    await expect(
      page.getByText("Shared finding", { exact: true })
    ).toBeVisible();
    await page
      .getByRole("button", { name: "1 Annotation", exact: true })
      .click();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();

    check =
      "selected-only cycle retains native plural membership and label modes";
    const selectedEntry = new URL(mouseEntry);
    selectedEntry.searchParams.set(
      "ann",
      [mouseIds[0], mouseIds[1], mouseIds[3]].join(",")
    );
    await page.goto(selectedEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await expect(highlights).toHaveCount(5);
    await settlePages();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Show selected only", exact: true })
      .click();
    await expect(highlights).toHaveCount(3);
    const selectionBefore = new URL(page.url()).searchParams.get("ann");
    await sourceHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const selectedBox = await sourceHighlight.boundingBox();
    const selectedPoint = {
      x: selectedBox.x + selectedBox.width / 6,
      y: selectedBox.y + selectedBox.height / 2,
    };
    for (const index of [1, 3, 0]) {
      await inspect(selectedPoint, index);
      await expect(highlights).toHaveCount(3);
      assert.equal(
        new URL(page.url()).searchParams.get("ann"),
        selectionBefore
      );
    }
    const selectedCanvas = await pane.locator("canvas").nth(1).boundingBox();
    await page.mouse.click(
      selectedCanvas.x + selectedCanvas.width - 30,
      selectedPoint.y
    );
    await page.mouse.move(1400, 30);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    await expect(highlights).toHaveCount(3);
    assert.equal(new URL(page.url()).searchParams.get("ann"), selectionBefore);
    await inspect(selectedPoint, 0);
    await page
      .getByRole("button", { name: "HIDE labels", exact: true })
      .click();
    await page.mouse.click(selectedPoint.x, selectedPoint.y);
    await page.mouse.move(1400, 30);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    await expect(highlights).toHaveCount(3);
    assert.equal(await mouseCards.nth(1).getAttribute("aria-current"), "true");
    await page
      .getByRole("button", { name: "ALWAYS labels", exact: true })
      .click();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      3
    );
    await expect(highlights).toHaveCount(3);
    assert.equal(new URL(page.url()).searchParams.get("ann"), selectionBefore);
    await page
      .getByRole("button", { name: "Default labels", exact: true })
      .click();
    await expect(highlights).toHaveCount(5);
    await settlePages();

    check =
      "native drag from saved evidence copies source text without cycling";
    if (name === "chromium")
      await page
        .context()
        .grantPermissions(["clipboard-read", "clipboard-write"]);
    const dragBox = await sourceHighlight.boundingBox();
    await page.mouse.move(
      dragBox.x + 20 * scale,
      dragBox.y + dragBox.height / 2
    );
    await page.mouse.down();
    await page.mouse.move(
      dragBox.x + 145 * scale,
      dragBox.y + dragBox.height / 2,
      { steps: 8 }
    );
    await page.mouse.up();
    await page
      .getByTestId("selection-action-menu")
      .waitFor({ state: "visible" });
    await page.getByTestId("copy-text-button").click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toBe("Shared passage.");
    await page.mouse.move(1400, 30);
    await expect(evidenceLabel(1)).toBeVisible();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      1
    );

    check = "drag outside the PDF and back does not cycle evidence";
    const excursionBox = await sourceHighlight.boundingBox();
    const excursion = {
      x: excursionBox.x + excursionBox.width / 6,
      y: excursionBox.y + excursionBox.height / 2,
    };
    await page.mouse.move(excursion.x, excursion.y);
    await page.mouse.down();
    await page.mouse.move(1400, 30);
    await page.mouse.move(excursion.x + 1, excursion.y);
    await page.mouse.up();
    await page.mouse.move(1400, 30);
    await expect(mouseCards.nth(1)).toHaveAttribute("aria-current", "true");
    await expect(evidenceLabel(1)).toBeVisible();
    if (await page.getByTestId("selection-action-menu").count())
      await page.getByTestId("cancel-button").click();

    check = "native PDF URL link keeps evidence focus";
    const nativeLink = page
      .getByRole("link", {
        name: "https://example.invalid/evidence",
        exact: true,
      })
      .nth(1);
    const linkBox = await nativeLink.boundingBox();
    const linkEvidenceBox = await page
      .locator(`[id="SELECTION_${mouseIds[4]}"]`)
      .boundingBox();
    const linkPoint = {
      x:
        (Math.max(linkBox.x, linkEvidenceBox.x) +
          Math.min(
            linkBox.x + linkBox.width,
            linkEvidenceBox.x + linkEvidenceBox.width
          )) /
        2,
      y:
        (Math.max(linkBox.y, linkEvidenceBox.y) +
          Math.min(
            linkBox.y + linkBox.height,
            linkEvidenceBox.y + linkEvidenceBox.height
          )) /
        2,
    };
    await page.mouse.move(linkPoint.x, linkPoint.y);
    await expect(evidenceLabel(4)).toBeVisible();
    await expect(evidenceLabel(1)).toBeVisible();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      2
    );
    const [popup, request] = await Promise.all([
      page.waitForEvent("popup"),
      page.context().waitForEvent("request", {
        predicate: (request) =>
          request.isNavigationRequest() &&
          request.url() === "https://example.invalid/evidence",
      }),
      page.mouse.click(linkPoint.x, linkPoint.y),
    ]);
    assert.equal(request.url(), "https://example.invalid/evidence");
    await popup.close();
    await page.mouse.move(1400, 30);
    await expect(evidenceLabel(1)).toBeVisible();

    check = "stationary background clears only evidence focus";
    await page
      .getByRole("button", { name: "Toggle Extract pane", exact: true })
      .click();
    const canvas = pane.locator("canvas").nth(1);
    const canvasBox = await canvas.boundingBox();
    const paneBox = await pane.boundingBox();
    assert.ok(paneBox.x + paneBox.width > canvasBox.x + canvasBox.width + 40);
    await page.mouse.click(canvasBox.x + canvasBox.width + 40, selectedPoint.y);
    await page.mouse.move(1400, 30);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    await expect(page.getByTestId("extract-pane")).toHaveCount(0);
    await expect(page.getByTestId("selection-action-menu")).toHaveCount(0);
    check = "native Shift queued selection keeps source-text selection";
    await page.goto(mouseEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await expect(highlights).toHaveCount(5);
    await settlePages();
    await sourceHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const shiftBox = await sourceHighlight.boundingBox();
    const shiftScale = shiftBox.width / 150;
    const shiftY = shiftBox.y + shiftBox.height / 2;
    await page.keyboard.down("Shift");
    await page.mouse.move(shiftBox.x - 10 * shiftScale, shiftY);
    await page.mouse.down();
    await page.mouse.move(shiftBox.x + 65 * shiftScale, shiftY, { steps: 8 });
    await page.mouse.up();
    await page.keyboard.up("Shift");
    await expect(
      pane.locator('#selection-layer [id^="SELECTION_"]')
    ).toHaveCount(1);
    await expect(page.getByTestId("selection-action-menu")).toHaveCount(0);
    await page.mouse.move(1400, 30);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );

    check = "native annotation creation after dragging retains evidence focus";
    const editableEntry = new URL(mouseEntry);
    editableEntry.searchParams.set("editable", "1");
    await page.goto(editableEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await expect(highlights).toHaveCount(5);
    await settlePages();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await sourceHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const createBox = await sourceHighlight.boundingBox();
    await page.mouse.click(
      createBox.x + createBox.width / 6,
      createBox.y + createBox.height / 2
    );
    await page.mouse.move(1400, 30);
    await evidenceLabel(0).waitFor({ state: "visible" });
    await page
      .getByRole("button", { name: "Choose manual label", exact: true })
      .click();
    await page.mouse.move(
      createBox.x + createBox.width * 0.13,
      createBox.y + createBox.height / 2
    );
    await page.mouse.down();
    await page.mouse.move(
      createBox.x + createBox.width * 0.96,
      createBox.y + createBox.height / 2,
      { steps: 8 }
    );
    await page.mouse.up();
    await page.getByTestId("apply-label-button").click();
    await expect(highlights).toHaveCount(6);
    await page.mouse.move(1400, 30);
    await expect(evidenceLabel(0)).toBeVisible();
    assert.equal(await mouseCards.first().getAttribute("aria-current"), "true");
    await page
      .getByRole("button", { name: "ALWAYS labels", exact: true })
      .click();
    await expect(
      page.locator('[data-annotation-label="QW5ub3RhdGlvblR5cGU6NjA="]')
    ).toHaveText(/Created manual/);

    check = "native child dialog owns pointer actions inside fullscreen viewer";
    const dialogEntry = new URL(editableEntry);
    dialogEntry.searchParams.set("native-dialog", "1");
    await page.goto(dialogEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "View manual annotations", exact: true })
      .click();
    await expect(highlights).toHaveCount(1);
    await settlePages();
    const manualHighlight = highlights.first();
    const manualId = (await manualHighlight.getAttribute("id")).slice(
      "SELECTION_".length
    );
    const manualLabel = page.locator(`[data-annotation-label="${manualId}"]`);
    await manualHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const manualBox = await manualHighlight.boundingBox();
    await page.mouse.click(
      manualBox.x + manualBox.width / 2,
      manualBox.y + manualBox.height / 2
    );
    await page.mouse.move(1400, 30);
    await manualLabel.waitFor({ state: "visible" });
    const edit = manualLabel.getByRole("button", {
      name: "Edit label: Document A manual",
      exact: true,
    });
    const editBox = await edit.boundingBox();
    await page.mouse.click(
      editBox.x + editBox.width / 2,
      editBox.y + editBox.height / 2
    );
    const childDialog = page.getByRole("dialog").filter({
      has: page.getByText("Edit Label", { exact: true }),
    });
    await expect(childDialog).toHaveCount(1);
    await expect(childDialog).toBeVisible();
    const title = childDialog.getByText("Edit Label", { exact: true });
    await expect
      .poll(() =>
        title.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          return element.contains(
            document.elementFromPoint(
              rect.left + rect.width / 2,
              rect.top + rect.height / 2
            )
          );
        })
      )
      .toBe(true);
    const titleBox = await title.boundingBox();
    const dialogScroll = await pane.evaluate((element) => element.scrollTop);
    const dialogSelection = new URL(page.url()).searchParams.get("ann");
    await page.mouse.click(
      titleBox.x + titleBox.width / 2,
      titleBox.y + titleBox.height / 2
    );
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(250); // Temporary pointer visibility must expire.
    await expect(childDialog).toBeVisible();
    await expect(manualLabel).toBeVisible();
    await expect(page.getByTestId("selection-action-menu")).toHaveCount(0);
    const cancelBox = await childDialog
      .getByRole("button", { name: "Cancel", exact: true })
      .boundingBox();
    await page.mouse.click(
      cancelBox.x + cancelBox.width / 2,
      cancelBox.y + cancelBox.height / 2
    );
    await expect(childDialog).toHaveCount(0);
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(250);
    await expect(manualLabel).toBeVisible();
    await expect(highlights).toHaveCount(1);
    assert.equal(new URL(page.url()).searchParams.get("ann"), dialogSelection);
    assert.equal(
      await pane.evaluate((element) => element.scrollTop),
      dialogScroll
    );

    check = "dense Always labels expose their native edit controls";
    const denseEntry = new URL(editableEntry);
    denseEntry.searchParams.set("dense-control", "1");
    await page.goto(denseEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "View manual annotations", exact: true })
      .click();
    await expect(highlights).toHaveCount(5);
    await page
      .getByRole("button", { name: "Set zoom 127%", exact: true })
      .click();
    await expect(page.getByLabel("Zoom", { exact: true })).toHaveText("1.27");
    await expect
      .poll(
        async () =>
          (await pane.locator("canvas").first().boundingBox())?.height ?? 0
      )
      .toBeGreaterThan(1000);
    const densePaneBox = await pane.boundingBox();
    await page.mouse.move(densePaneBox.x + 100, densePaneBox.y + 200);
    await page.mouse.wheel(0, -1000);
    await expect
      .poll(() => pane.evaluate((element) => element.scrollTop))
      .toBe(0);
    const denseC = page.locator('[id="SELECTION_QW5ub3RhdGlvblR5cGU6NDE="]');
    const denseCLabel = page.locator(
      '[data-annotation-label="QW5ub3RhdGlvblR5cGU6NDE="]'
    );
    const denseCBox = await denseC.boundingBox();
    await page.mouse.click(
      denseCBox.x + denseCBox.width * 0.6,
      denseCBox.y + denseCBox.height * 0.8
    );
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(250);
    await expect(denseCLabel).toBeVisible();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      1
    );
    await page
      .getByRole("button", { name: "ALWAYS labels", exact: true })
      .click();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      5
    );
    await expect
      .poll(() =>
        pane.evaluate((element) => {
          const viewport = element.getBoundingClientRect();
          return [...element.querySelectorAll("[data-annotation-label]")].every(
            (label) => {
              const rect = label.getBoundingClientRect();
              return (
                rect.height > 10 &&
                rect.top >= viewport.top &&
                rect.bottom <= viewport.bottom
              );
            }
          );
        })
      )
      .toBe(true);
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(250);
    const denseScroll = await pane.evaluate((element) => element.scrollTop);
    const denseUrl = page.url();
    // C is the independently reproduced counterexample; every other displayed
    // bar must also retain its own native editor through ordinary transfer.
    for (const [number, text] of [
      [41, "Section Header"],
      [11, "Party names and addresses"],
      [12, "Hire purchase agreement title"],
      [42, "Paragraph"],
      [43, "Hire purchase agreement title"],
    ]) {
      check = `dense Always native edit control ${number}`;
      const label = page.locator(
        `[data-annotation-label="${Buffer.from(
          `AnnotationType:${number}`
        ).toString("base64")}"]`
      );
      const denseEdit = label.getByRole("button", {
        name: `Edit label: ${text}`,
        exact: true,
      });
      await page.mouse.move(1400, 30);
      await page.waitForTimeout(250);
      const denseEditBox = await denseEdit.boundingBox();
      await page.mouse.move(
        denseEditBox.x + denseEditBox.width / 2,
        denseEditBox.y + denseEditBox.height / 2
      );
      await page.waitForTimeout(250);
      denseControlObservation = await denseEdit.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const hit = document.elementFromPoint(
          rect.left + rect.width / 2,
          rect.top + rect.height / 2
        );
        return {
          controlBounds: rect.toJSON(),
          hitTag: hit?.tagName,
          hitId: hit?.closest('[id^="SELECTION_"]')?.id,
          intendedControlHit: element.contains(hit),
        };
      });
      await page.mouse.click(
        denseEditBox.x + denseEditBox.width / 2,
        denseEditBox.y + denseEditBox.height / 2
      );
      const denseEditor = page.getByRole("dialog").filter({
        has: page.getByText("Edit Label", { exact: true }),
      });
      await expect(denseEditor).toBeVisible();
      if (number === 41 && process.env.EVIDENCE_ARTIFACT_DIRECTORY)
        await page.screenshot({
          path: `${process.env.EVIDENCE_ARTIFACT_DIRECTORY}/dense-control-green-${name}.png`,
        });
      const denseCancelBox = await denseEditor
        .getByRole("button", { name: "Cancel", exact: true })
        .boundingBox();
      await page.mouse.click(
        denseCancelBox.x + denseCancelBox.width / 2,
        denseCancelBox.y + denseCancelBox.height / 2
      );
      await expect(denseEditor).toHaveCount(0);
      assert.equal(page.url(), denseUrl);
      assert.equal(
        await pane.evaluate((element) => element.scrollTop),
        denseScroll
      );
    }
    await page
      .getByRole("button", { name: "Default labels", exact: true })
      .click();
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(250);
    await expect(denseCLabel).toBeVisible();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      1
    );
    check = "native Add link dialog controls remain reachable over fullscreen";
    await page.goto(editableEntry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await expect(highlights).toHaveCount(5);
    await settlePages();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await sourceHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const urlSourceBox = await sourceHighlight.boundingBox();
    const urlY = urlSourceBox.y + urlSourceBox.height / 2;
    await page.mouse.click(urlSourceBox.x + urlSourceBox.width / 6, urlY);
    await page.mouse.move(1400, 30);
    await evidenceLabel(0).waitFor({ state: "visible" });
    await page.mouse.move(urlSourceBox.x + urlSourceBox.width * 0.13, urlY);
    await page.mouse.down();
    await page.mouse.move(urlSourceBox.x + urlSourceBox.width * 0.96, urlY, {
      steps: 8,
    });
    await page.mouse.up();
    const addLink = page.getByTestId("create-link-button");
    await expect(addLink).toBeVisible();
    const addLinkBox = await addLink.boundingBox();
    const urlScroll = await pane.evaluate((element) => element.scrollTop);
    const urlLocation = page.url();
    await page.mouse.click(
      addLinkBox.x + addLinkBox.width / 2,
      addLinkBox.y + addLinkBox.height / 2
    );
    const urlDialog = page.getByRole("dialog").filter({
      has: page.getByText("Add link", { exact: true }),
    });
    await expect(urlDialog).toBeVisible();
    const createLink = urlDialog.getByRole("button", {
      name: "Create link",
      exact: true,
    });
    const createLinkBox = await createLink.boundingBox();
    await page.mouse.move(1400, 30);
    await page.mouse.move(
      createLinkBox.x + createLinkBox.width / 2,
      createLinkBox.y + createLinkBox.height / 2
    );
    await page.waitForTimeout(250);
    urlDialogObservation = await createLink.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2
      );
      return {
        controlBounds: rect.toJSON(),
        hitTag: hit?.tagName,
        hitDialog: hit?.closest('[role="dialog"]')?.id,
        intendedControlHit: element.contains(hit),
      };
    });
    // Empty and invalid input exercise real native controls without a save.
    await page.mouse.click(
      createLinkBox.x + createLinkBox.width / 2,
      createLinkBox.y + createLinkBox.height / 2
    );
    await expect(
      urlDialog.getByText("URL is required.", { exact: true })
    ).toBeVisible();
    if (process.env.EVIDENCE_ARTIFACT_DIRECTORY)
      await page.screenshot({
        path: `${process.env.EVIDENCE_ARTIFACT_DIRECTORY}/native-url-dialog-green-${name}.png`,
      });
    const targetUrl = urlDialog.getByLabel("Target URL", { exact: true });
    const targetBox = await targetUrl.boundingBox();
    await page.mouse.click(
      targetBox.x + targetBox.width / 2,
      targetBox.y + targetBox.height / 2
    );
    await expect(targetUrl).toBeFocused();
    await page.keyboard.type("unsafe-target");
    await expect(targetUrl).toHaveValue("unsafe-target");
    const invalidCreateBox = await createLink.boundingBox();
    await page.mouse.click(
      invalidCreateBox.x + invalidCreateBox.width / 2,
      invalidCreateBox.y + invalidCreateBox.height / 2
    );
    await expect(
      urlDialog.getByText(
        "URL must start with http://, https://, or '/' (site-relative path).",
        { exact: true }
      )
    ).toBeVisible();
    const urlCancelBox = await urlDialog
      .getByRole("button", { name: "Cancel", exact: true })
      .boundingBox();
    await page.mouse.click(
      urlCancelBox.x + urlCancelBox.width / 2,
      urlCancelBox.y + urlCancelBox.height / 2
    );
    await expect(urlDialog).toHaveCount(0);
    await page.mouse.move(1400, 30);
    await page.waitForTimeout(250);
    await expect(evidenceLabel(0)).toBeVisible();
    assert.equal(await mouseCards.first().getAttribute("aria-current"), "true");
    assert.equal(page.url(), urlLocation);
    assert.equal(
      await pane.evaluate((element) => element.scrollTop),
      urlScroll
    );

    results.push({
      browser: name,
      version: browser.version(),
      ok: true,
      viewport: "1440x1000",
      pdfZoom: zoomBeforeCycle,
      checks: [
        "full overlap stable identity cycle",
        "pane source emphasis and retained viewport",
        "partial overlap/out-of-set/no transitive cycle",
        "shared hover readability and separate native action cancellation",
        "label exclusions",
        "pane finding retention",
        "selected-only membership/Hide/Always",
        "native source drag/copy",
        "drag outside and back",
        "native PDF link hover/activation",
        "native Shift queued selection",
        "closed-pane stationary background",
        "native annotation creation",
        "native child dialog ownership and cancellation",
        "dense Always native edit control ownership",
        "native Add link dialog input/validation/cancellation",
      ],
    });
  } catch (error) {
    if (process.env.EVIDENCE_ARTIFACT_DIRECTORY)
      await page.screenshot({
        path: `${process.env.EVIDENCE_ARTIFACT_DIRECTORY}/mouse-failure-${name}.png`,
      });
    results.push({
      browser: name,
      ok: false,
      check,
      error: String(error),
      ...(denseControlObservation ? { denseControlObservation } : {}),
      ...(urlDialogObservation ? { urlDialogObservation } : {}),
      screen: {
        zoom: await page.getByLabel("Zoom", { exact: true }).textContent(),
        windowY: await page.evaluate(() => window.scrollY),
        paneTop: await page
          .getByTestId("pdf-pane")
          .evaluate((element) => element.scrollTop),
        evidence: await page
          .locator('[id^="SELECTION_"]:not([id^="SELECTION_TOKEN_"])')
          .evaluateAll((elements) =>
            elements.map((element) => ({
              id: element.id,
              bounds: element.getBoundingClientRect().toJSON(),
            }))
          ),
      },
    });
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify(results));
if (results.some((result) => !result.ok)) process.exitCode = 1;
