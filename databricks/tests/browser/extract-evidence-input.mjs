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
  page.setDefaultTimeout(10000);
  let check = "keyboard reachability and temporary label inspection";
  let tabObservations = [];
  let inputPage = page;
  let touchObservation;
  const nativeControlObservations = [];
  const keyboardPointObservations = [];
  const screenshots = [];
  const capture = async (artifact) => {
    if (process.env.EVIDENCE_ARTIFACT_DIRECTORY) {
      screenshots.push({
        file: `${artifact}-${name}.png`,
        viewport: inputPage.viewportSize(),
        pdfZoom: Number(
          await inputPage.getByLabel("Zoom", { exact: true }).textContent()
        ),
        focusedCards: await inputPage
          .locator(
            '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
          )
          .evaluateAll((nodes) =>
            nodes.map((node) => node.getAttribute("data-annotation-id"))
          ),
      });
      await inputPage.screenshot({
        path: `${process.env.EVIDENCE_ARTIFACT_DIRECTORY}/${artifact}-${name}.png`,
      });
    }
  };
  try {
    const entry = new URL(process.env.EVIDENCE_TEST_URL);
    entry.searchParams.set("mouse", "1");
    await page.goto(entry.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    const pane = page.getByTestId("pdf-pane");
    const highlights = pane.locator(
      '[id^="SELECTION_"]:not([id^="SELECTION_TOKEN_"])'
    );
    await expect(highlights).toHaveCount(5);
    await expect
      .poll(
        async () =>
          (await pane.locator("canvas").first().boundingBox())?.height ?? 0
      )
      .toBeGreaterThan(1200);
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    const cards = page.locator(
      '[data-testid="extract-pane"] [data-annotation-id]'
    );
    const ids = await cards.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("data-annotation-id"))
    );
    const label = (index) =>
      page.locator(`[data-annotation-label="${ids[index]}"]`);
    await page.mouse.move(1400, 30);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    let reached;
    for (let count = 0; count < 70; count++) {
      await page.keyboard.press("Shift+Tab");
      const active = await page.evaluate(() => document.activeElement?.id);
      tabObservations.push(
        await page.evaluate(() => ({
          tag: document.activeElement?.tagName,
          id: document.activeElement?.id,
          name: document.activeElement?.getAttribute("aria-label"),
          targets: [
            ...document.querySelectorAll("[data-pdf-evidence-target]"),
          ].map((element) => ({
            id: element.id,
            tabIndex: element.tabIndex,
            bounds: element.getBoundingClientRect().toJSON(),
          })),
        }))
      );
      if (
        active?.startsWith("SELECTION_") &&
        !active.startsWith("SELECTION_TOKEN_")
      ) {
        reached = active.slice("SELECTION_".length);
        break;
      }
    }
    assert.ok(
      reached,
      "real Tab traversal reaches a visible evidence highlight"
    );
    await expect(
      page.locator(`[data-annotation-label="${reached}"]`)
    ).toBeVisible();
    assert.equal(
      await page
        .locator(
          '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
        )
        .count(),
      0
    );
    await capture("keyboard-temporary-label");
    for (let count = 0; count < 10; count++) {
      await page.keyboard.press("Tab");
      const stillOwned = await page.evaluate(
        (id) =>
          document.activeElement?.id === `SELECTION_${id}` ||
          document.activeElement
            ?.closest("[data-annotation-label]")
            ?.getAttribute("data-annotation-label") === id,
        reached
      );
      if (!stillOwned) break;
    }
    await expect(
      page.locator(`[data-annotation-label="${reached}"]`)
    ).toBeHidden();
    const checks = [check];
    check =
      "temporary label's native actions are keyboard reachable without evidence activation";
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    assert.equal(
      await page.evaluate(
        (id) =>
          document.activeElement
            ?.closest("[data-annotation-label]")
            ?.getAttribute("data-annotation-label") === id,
        reached
      ),
      true
    );
    await page.keyboard.press("Enter");
    await expect(
      page.locator(`[data-annotation-label="${reached}"]`).getByRole("button", {
        name: "Login to see available actions!",
        exact: true,
      })
    ).toBeVisible();
    await capture("keyboard-native-actions");
    assert.equal(
      await page
        .locator(
          '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
        )
        .count(),
      0
    );
    checks.push(check);
    check =
      "native annotation actions consume Escape from their keyboard action";
    await page.keyboard.press("Tab");
    assert.equal(
      await page.evaluate(() => document.activeElement?.tagName),
      "BUTTON"
    );
    await page.keyboard.press("Escape");
    await expect(
      page.locator(`[data-annotation-label="${reached}"]`).getByRole("button", {
        name: "Login to see available actions!",
        exact: true,
      })
    ).toHaveCount(0);
    assert.equal(
      await page.evaluate(() =>
        document.activeElement?.getAttribute("aria-label")
      ),
      "Annotation actions"
    );
    checks.push(check);
    check =
      "eligible PDF Escape clears singular focus without navigation or saved-selection changes";
    await page.keyboard.press("Escape");
    await cards.nth(2).click();
    const first = pane.locator(`[id="SELECTION_${ids[0]}"]`);
    await first.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const box = await first.boundingBox();
    await page.mouse.click(box.x + box.width / 6, box.y + box.height / 2);
    await page.mouse.move(1400, 30);
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    const route = () => {
      // Native routing may reorder query keys while delivering a source entry.
      // Every path, key and value remains part of the navigation assertion.
      const current = new URL(page.url());
      current.searchParams.sort();
      return current.pathname + current.search;
    };
    const beforeEscape = {
      url: route(),
      scroll: await pane.evaluate((element) => element.scrollTop),
      zoom: await page.getByLabel("Zoom", { exact: true }).textContent(),
    };
    await page.keyboard.press("Escape");
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    assert.equal(route(), beforeEscape.url);
    assert.equal(
      await pane.evaluate((element) => element.scrollTop),
      beforeEscape.scroll
    );
    assert.equal(
      await page.getByLabel("Zoom", { exact: true }).textContent(),
      beforeEscape.zoom
    );
    await capture("escape-clears-persistent-focus");
    checks.push(check);
    check =
      "pending native mouse selection owns first Escape before evidence focus";
    await page.mouse.click(box.x + box.width / 6, box.y + box.height / 2);
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    await page.mouse.down();
    await page.keyboard.press("Escape");
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    await page.mouse.up();
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    await page.keyboard.press("Escape");
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    checks.push(check);
    check =
      "active native mouse text selection consumes Escape before evidence focus";
    await page.mouse.click(box.x + box.width / 6, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.9, box.y + box.height / 2);
    await page.keyboard.press("Escape");
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    await page.mouse.up();
    await expect(page.getByText("Copy Text", { exact: true })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    checks.push(check);
    check =
      "Enter and Space use full and partial point candidates and preserve source context";
    const tabTo = async (index, direction = "Shift+Tab") => {
      for (let count = 0; count < 100; count++) {
        if (
          await page.evaluate(
            (id) => document.activeElement?.id === `SELECTION_${id}`,
            ids[index]
          )
        )
          return;
        await page.keyboard.press(direction);
      }
      assert.fail(`keyboard traversal reaches evidence ${index}`);
    };
    await cards.nth(2).click();
    // Native source navigation synchronizes its annotation URL asynchronously.
    // Complete that public navigation before preserving its context while inspecting.
    await expect
      .poll(() => new URL(page.url()).searchParams.get("ann"))
      .toBe(ids[2]);
    await expect(cards.nth(2)).toHaveAttribute("aria-current", "true");
    await expect(pane.locator(`[id="SELECTION_${ids[2]}"]`)).toHaveCSS(
      "background-color",
      "rgba(37, 99, 235, 0.18)"
    );
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve))
        )
    );
    await expect(cards.nth(2)).toHaveAttribute("aria-current", "true");
    await tabTo(0);
    const keyboardRoute = route();
    const keyboardScroll = await pane.evaluate((element) => element.scrollTop);
    for (const [key, index] of [
      ["Enter", 0],
      ["Space", 1],
      ["Enter", 3],
      ["Space", 0],
    ]) {
      keyboardPointObservations.push(
        await page.evaluate(
          ({ key, index }) => {
            const target = document.activeElement;
            const rect = target.getBoundingClientRect();
            const x = rect.left + rect.width / 2,
              y = rect.top + rect.height / 2;
            return {
              key,
              index,
              active: target.id,
              rect: rect.toJSON(),
              canvas: [
                ...document.querySelectorAll('[data-testid="pdf-pane"] canvas'),
              ].map((node) => node.getBoundingClientRect().toJSON()),
              mountedPointCandidates: [
                ...document.querySelectorAll("[data-pdf-evidence-target]"),
              ]
                .filter((node) => {
                  const b = node.getBoundingClientRect();
                  return (
                    x >= b.left && x <= b.right && y >= b.top && y <= b.bottom
                  );
                })
                .map((node) => node.getAttribute("data-pdf-evidence-target")),
              focused: [
                ...document.querySelectorAll(
                  '[data-testid="extract-pane"] [aria-current="true"]'
                ),
              ].map((node) => node.getAttribute("data-annotation-id")),
            };
          },
          { key, index }
        )
      );
      await page.keyboard.press(key);
      await expect(cards.nth(index)).toHaveAttribute("aria-current", "true");
      assert.equal(route(), keyboardRoute);
      assert.equal(
        await pane.evaluate((element) => element.scrollTop),
        keyboardScroll
      );
    }
    await tabTo(2, "Tab"); // C's center is its exclusive part, outside A/B/D and E.
    await page.keyboard.press("Enter");
    await expect(cards.nth(2)).toHaveAttribute("aria-current", "true");
    await tabTo(4, "Tab"); // Strictly transitive E remains its own center candidate.
    await page.keyboard.press("Space");
    await expect(cards.nth(4)).toHaveAttribute("aria-current", "true");
    await tabTo(0);
    await page.keyboard.press("Enter");
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    await capture("keyboard-overlap-cycle");
    checks.push(check);
    const filterToggle = page.getByTestId("annotation-controls-toggle");
    const observeControls = async (stage) => {
      nativeControlObservations.push({
        stage,
        focused: await cards.evaluateAll((nodes) =>
          nodes
            .filter((node) => node.getAttribute("aria-current") === "true")
            .map((node) => node.getAttribute("data-annotation-id"))
        ),
        active: await page.evaluate(() => ({
          tag: document.activeElement?.tagName,
          id: document.activeElement?.id,
          rect: document.activeElement?.getBoundingClientRect().toJSON(),
          parent: document.activeElement?.parentElement?.outerHTML.slice(
            0,
            250
          ),
        })),
        labels: await page
          .locator("[data-annotation-label]:visible")
          .evaluateAll((nodes) =>
            nodes.map((node) => node.getAttribute("data-annotation-label"))
          ),
      });
    };
    const setMode = async (mode) => {
      await observeControls(`before ${mode}`);
      await filterToggle.click();
      await expect(filterToggle).toHaveAttribute("aria-expanded", "true");
      await page.getByRole("combobox").first().click();
      await page.getByRole("option", { name: mode, exact: true }).click();
      await expect(page.getByRole("combobox").first()).toContainText(mode);
      await filterToggle.click();
      await expect(filterToggle).toHaveAttribute("aria-expanded", "false");
      await observeControls(`after ${mode}`);
    };
    check =
      "keyboard inspection respects native Hide and remembered label exclusions";
    await setMode("Hide");
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    await expect(cards.first()).toHaveAttribute("aria-current", "true");
    await tabTo(0, "Tab");
    await observeControls("Hide target before Space");
    await page.keyboard.press("Space");
    await observeControls("Hide target after Space");
    await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    const toggleLabels = async () => {
      await filterToggle.click();
      await page.getByRole("combobox").nth(1).click();
      await page
        .getByRole("option", { name: "Evidence A", exact: true })
        .click();
      await page
        .getByRole("option", { name: "Evidence C", exact: true })
        .click();
      await filterToggle.click();
      await expect(filterToggle).toHaveAttribute("aria-expanded", "false");
    };
    await toggleLabels();
    await expect(pane.locator(`[id="SELECTION_${ids[1]}"]`)).toHaveCount(0);
    await toggleLabels();
    await expect(highlights).toHaveCount(5);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    await setMode("On Hover");
    await expect(label(1)).toBeVisible();
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      1
    );
    checks.push(check);
    check =
      "keyboard evidence focus survives native selected-only, zoom and pane transitions";
    await filterToggle.click();
    const selectedOnly = page.getByRole("checkbox", {
      name: "Show Only Selected",
      exact: true,
    });
    await selectedOnly.locator("..").click();
    await expect(selectedOnly).toBeChecked();
    await filterToggle.click();
    await expect(highlights).toHaveCount(1);
    await expect(page.locator("[data-annotation-label]:visible")).toHaveCount(
      0
    );
    await filterToggle.click();
    await selectedOnly.locator("..").click();
    await expect(selectedOnly).not.toBeChecked();
    await filterToggle.click();
    await expect(highlights).toHaveCount(5);
    await expect(label(1)).toBeVisible();
    const beforeZoom = Number(
      await page.getByLabel("Zoom", { exact: true }).textContent()
    );
    await page.keyboard.press("Control+=");
    await expect
      .poll(async () =>
        Number(await page.getByLabel("Zoom", { exact: true }).textContent())
      )
      .toBe(beforeZoom + 0.1);
    await expect(label(1)).toBeVisible();
    await page
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await expect(page.getByTestId("extract-pane")).toHaveCount(0);
    await expect(label(1)).toBeVisible();
    await page
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
    checks.push(check);
    check =
      "native viewer settings own Escape before closed-pane evidence focus";
    await page
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    const nativeSettings = page.getByTestId("settings-button");
    await nativeSettings.click();
    await expect(page.getByTestId("settings-panel")).toBeVisible();
    await tabTo(0, "Tab");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("settings-panel")).toHaveCount(0);
    await expect(label(1)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(label(1)).toBeHidden();
    await page
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    await cards.nth(1).click();
    await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
    checks.push(check);
    check = "native width menu owns Escape only while it is displayed";
    const widthButton = page.getByRole("button", {
      name: "Panel width",
      exact: true,
    });
    await widthButton.click();
    await expect(page.getByTestId("width-menu-panel")).toBeVisible();
    await tabTo(0, "Tab");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("width-menu-panel")).toHaveCount(0);
    await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
    await widthButton.click();
    await expect(page.getByTestId("width-menu-panel")).toBeVisible();
    await page
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await expect(page.getByTestId("extract-pane")).toHaveCount(0);
    await expect(page.getByTestId("width-menu-panel")).toHaveCount(0);
    await tabTo(0, "Tab");
    await page.keyboard.press("Escape");
    await expect(label(1)).toBeHidden();
    await page
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await page
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    await cards.nth(1).click();
    await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
    checks.push(check);
    check =
      "native filter owns first Escape and subsequent PDF Escape clears focus";
    await filterToggle.click();
    await expect(filterToggle).toHaveAttribute("aria-expanded", "true");
    await tabTo(0, "Tab");
    await page.keyboard.press("Escape");
    await expect(filterToggle).toHaveAttribute("aria-expanded", "false");
    await expect(cards.nth(1)).toHaveAttribute("aria-current", "true");
    await page.keyboard.press("Escape");
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    checks.push(check);
    check =
      "temporary keyboard label survives its native child dialog and restores its launcher";
    const editable = new URL(entry);
    editable.searchParams.set("editable", "1");
    editable.searchParams.set("dense-control", "1");
    await page.goto(editable.toString());
    await page.getByText("Document A", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "View manual annotations", exact: true })
      .click();
    await expect(highlights).toHaveCount(5);
    await expect
      .poll(
        async () =>
          (await pane.locator("canvas").first().boundingBox())?.height ?? 0
      )
      .toBeGreaterThan(1200);
    // Manual mode prepares the editable fixture; native settings own mode changes.
    await setMode("Always Show");
    await expect(
      page.getByRole("button", { name: /^Edit label:/ })
    ).toHaveCount(5);
    await setMode("On Hover");
    let editableTarget;
    for (let count = 0; count < 70; count++) {
      await page.keyboard.press("Tab");
      const active = await page.evaluate(() => document.activeElement?.id);
      if (
        active?.startsWith("SELECTION_") &&
        !active.startsWith("SELECTION_TOKEN_")
      ) {
        editableTarget = active.slice("SELECTION_".length);
        break;
      }
    }
    assert.ok(editableTarget);
    const editableLabel = page.locator(
      `[data-annotation-label="${editableTarget}"]`
    );
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    const launcherName = await page.evaluate(() =>
      document.activeElement?.getAttribute("aria-label")
    );
    assert.match(launcherName, /^Edit label:/);
    await page.keyboard.press("Enter");
    const dialog = page
      .getByRole("dialog")
      .filter({ has: page.getByText("Edit Label", { exact: true }) });
    await expect(dialog).toBeVisible();
    const paintedDialog = async (region, cancellation) => {
      await expect
        .poll(() =>
          region.evaluate((node) => {
            let minimumOpacity = 1;
            for (let element = node; element; element = element.parentElement)
              minimumOpacity = Math.min(
                minimumOpacity,
                Number(getComputedStyle(element).opacity)
              );
            return minimumOpacity;
          })
        )
        .toBe(1);
      await region
        .getByRole("button", { name: cancellation, exact: true })
        .click({ trial: true });
    };
    await paintedDialog(dialog, "Cancel");
    await expect(editableLabel).toBeVisible();
    await capture("keyboard-native-child-dialog");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    assert.equal(
      await page.evaluate(() =>
        document.activeElement?.getAttribute("aria-label")
      ),
      launcherName
    );
    await expect(editableLabel).toBeVisible();
    await capture("keyboard-child-cancel-return");
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    checks.push(check);
    check =
      "temporary keyboard label survives protected native confirmation cancellation";
    await page.keyboard.press("Shift+Tab");
    await expect(
      editableLabel.getByRole("button", {
        name: "Annotation actions",
        exact: true,
      })
    ).toBeFocused();
    await page.keyboard.press("Enter");
    const deleteAction = editableLabel.getByRole("button", {
      name: "Delete Annotation",
      exact: true,
    });
    for (
      let count = 0;
      count < 5 &&
      !(await deleteAction.evaluate((node) => node === document.activeElement));
      count++
    ) {
      await page.keyboard.press("Tab");
    }
    await expect(deleteAction).toBeFocused();
    await page.keyboard.press("Enter");
    const confirmation = page.getByRole("dialog").filter({
      has: page.getByText("Are you sure you want to delete this annotation?", {
        exact: true,
      }),
    });
    await expect(confirmation).toBeVisible();
    await paintedDialog(confirmation, "No");
    await expect(editableLabel).toBeVisible();
    await capture("keyboard-protected-confirmation");
    // The native protected dialog names its cancellation control “No”.
    const cancelConfirmation = confirmation.getByRole("button", {
      name: "No",
      exact: true,
    });
    for (
      let count = 0;
      count < 5 &&
      !(await cancelConfirmation.evaluate(
        (node) => node === document.activeElement
      ));
      count++
    )
      await page.keyboard.press("Tab");
    await expect(cancelConfirmation).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(confirmation).toHaveCount(0);
    await expect(editableLabel).toBeVisible();
    await expect(
      editableLabel.getByRole("button", {
        name: "Annotation actions",
        exact: true,
      })
    ).toBeFocused();
    await expect(
      page.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    await capture("keyboard-protected-cancel-return");
    checks.push(check);
    check =
      "stationary touch overlap taps advance exactly one stable cycle step";
    const touchPage = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      hasTouch: true,
    });
    inputPage = touchPage;
    await touchPage.goto(entry.toString());
    await touchPage.getByText("Document A", { exact: true }).waitFor();
    const touchPane = touchPage.getByTestId("pdf-pane");
    await expect
      .poll(
        async () =>
          (await touchPane.locator("canvas").first().boundingBox())?.height ?? 0
      )
      .toBeGreaterThan(1200);
    await touchPage
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    const touchCards = touchPage.locator(
      '[data-testid="extract-pane"] [data-annotation-id]'
    );
    const touchHighlight = touchPane.locator(`[id="SELECTION_${ids[0]}"]`);
    await touchHighlight.evaluate((element) =>
      element.scrollIntoView({ block: "center", behavior: "instant" })
    );
    const touchBox = await touchHighlight.boundingBox();
    for (const index of [0, 1, 3, 0]) {
      await touchPage.touchscreen.tap(
        touchBox.x + touchBox.width / 6,
        touchBox.y + touchBox.height / 2
      );
      await expect(touchCards.nth(index)).toHaveAttribute(
        "aria-current",
        "true"
      );
      await expect(
        touchPage.locator(
          '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
        )
      ).toHaveCount(1);
    }
    await capture("stationary-touch-cycle");
    checks.push(check);
    if (name === "chromium") {
      check =
        "native held touch starting on saved evidence selects text without cycling";
      const cdp = await touchPage.context().newCDPSession(touchPage);
      const start = {
        x: touchBox.x + touchBox.width / 10,
        y: touchBox.y + touchBox.height / 2,
        id: 1,
      };
      await touchPage.evaluate(() => {
        window.inputTouchEvents = [];
        for (const type of [
          "touchstart",
          "touchmove",
          "touchend",
          "touchcancel",
          "mousedown",
          "mousemove",
          "mouseup",
          "pointerdown",
          "pointerup",
          "pointercancel",
        ])
          document.addEventListener(
            type,
            (event) =>
              window.inputTouchEvents.push({
                type,
                stamp: event.timeStamp,
                trusted: event.isTrusted,
                target: event.target.id,
                label: event.target
                  .closest("[data-annotation-label]")
                  ?.getAttribute("data-annotation-label"),
              }),
            true
          );
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [start],
      });
      await touchPage.waitForTimeout(650);
      touchObservation = await touchPage.evaluate(() => ({
        events: window.inputTouchEvents,
        layers: [...document.querySelectorAll("#selection-layer")].map(
          (layer) => ({
            touchAction: layer.style.touchAction,
            bounds: layer.getBoundingClientRect().toJSON(),
          })
        ),
      }));
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ ...start, x: touchBox.x + touchBox.width * 0.9 }],
      });
      await touchPage.waitForTimeout(50);
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      await expect(
        touchPage.getByText("Copy Text", { exact: true })
      ).toBeVisible();
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      await capture("native-held-touch-selection");
      await touchPage
        .context()
        .grantPermissions(["clipboard-read", "clipboard-write"]);
      await touchPage.getByText("Copy Text", { exact: true }).click();
      await expect
        .poll(() => touchPage.evaluate(() => navigator.clipboard.readText()))
        .toBe("Shared passage.");
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      checks.push(check);
      check = "cancelled touch discards pending native hold ownership";
      await touchPage.waitForTimeout(400);
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [start],
      });
      await touchPage.waitForTimeout(100);
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchCancel",
        touchPoints: [],
      });
      await touchPage.waitForTimeout(650);
      assert.equal(
        await touchPage
          .locator("#selection-layer")
          .evaluateAll((layers) =>
            layers.every((layer) => layer.style.touchAction === "auto")
          ),
        true
      );
      await expect(
        touchPage.getByText("Copy Text", { exact: true })
      ).toHaveCount(0);
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      checks.push(check);
      check =
        "pending native touch hold owns Escape without cycling on release";
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [start],
      });
      await touchPage.keyboard.press("Escape");
      await touchPage.waitForTimeout(550);
      assert.equal(
        await touchPage
          .locator("#selection-layer")
          .evaluateAll((layers) =>
            layers.every((layer) => layer.style.touchAction === "auto")
          ),
        true
      );
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      await expect(
        touchPage.getByText("Copy Text", { exact: true })
      ).toHaveCount(0);
      await capture("native-touch-escape");
      checks.push(check);
      check = "native moved touch retains evidence focus";
      const movementStarted = Date.now();
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [start],
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ ...start, x: start.x + 5 }],
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      await touchPage.waitForTimeout(200);
      touchObservation.smallMove = await touchPage.evaluate(
        (elapsed) => ({
          elapsed,
          events: window.inputTouchEvents,
          layers: [...document.querySelectorAll("#selection-layer")].map(
            (layer) => layer.style.touchAction
          ),
        }),
        Date.now() - movementStarted
      );
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      // Serial CDP acknowledgement can extend this movement beyond the hold
      // threshold. A genuine native held-selection menu is allowed in that case.
      if (await touchPage.getByText("Copy Text", { exact: true }).count())
        await touchPage.getByText("Cancel", { exact: true }).click();
      checks.push(check);
      check = "multi-touch discards native hold and does not advance evidence";
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [start, { ...start, x: start.x + 80, id: 2 }],
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      await touchPage.waitForTimeout(550);
      assert.equal(
        await touchPage
          .locator("#selection-layer")
          .evaluateAll((layers) =>
            layers.every((layer) => layer.style.touchAction === "auto")
          ),
        true
      );
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      await expect(
        touchPage.getByText("Copy Text", { exact: true })
      ).toHaveCount(0);
      checks.push(check);
      check =
        "genuine touch panning changes PDF scroll without cycling or a text menu";
      await touchPage.waitForTimeout(400);
      const beforePan = await touchPane.evaluate(
        (element) => element.scrollTop
      );
      touchObservation.panBefore = await touchPage.evaluate(() => ({
        events: window.inputTouchEvents,
        pane: document
          .querySelector('[data-testid="pdf-pane"]')
          .getBoundingClientRect()
          .toJSON(),
        scrollTop: document.querySelector('[data-testid="pdf-pane"]').scrollTop,
        max:
          document.querySelector('[data-testid="pdf-pane"]').scrollHeight -
          document.querySelector('[data-testid="pdf-pane"]').clientHeight,
      }));
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [{ x: 700, y: 700, id: 1 }],
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x: 700, y: 550, id: 1 }],
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x: 700, y: 400, id: 1 }],
      });
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      touchObservation.panAfter = await touchPage.evaluate(() => ({
        events: window.inputTouchEvents,
        scrollTop: document.querySelector('[data-testid="pdf-pane"]').scrollTop,
        layers: [...document.querySelectorAll("#selection-layer")].map(
          (layer) => layer.style.touchAction
        ),
      }));
      await expect
        .poll(async () =>
          Math.abs(
            (await touchPane.evaluate((element) => element.scrollTop)) -
              beforePan
          )
        )
        .toBeGreaterThan(100);
      await expect(touchCards.first()).toHaveAttribute("aria-current", "true");
      await expect(
        touchPage.getByText("Copy Text", { exact: true })
      ).toHaveCount(0);
      await capture("native-touch-pan");
      checks.push(check);
      await cdp.detach();
    }
    check =
      "stationary blank touch clears focused evidence with the extract pane closed";
    await touchPage
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await expect(touchPage.getByTestId("extract-pane")).toHaveCount(0);
    const blankBox = await touchPane.boundingBox();
    await touchPage.touchscreen.tap(
      blankBox.x + blankBox.width * 0.9,
      blankBox.y + blankBox.height * 0.8
    );
    await expect(
      touchPage.locator("[data-annotation-label]:visible")
    ).toHaveCount(0);
    await touchPage
      .getByRole("button", { name: "View extracts", exact: true })
      .click();
    await touchPage
      .getByRole("button", { name: "5 Annotations", exact: true })
      .click();
    await expect(
      touchPage.locator(
        '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
      )
    ).toHaveCount(0);
    await capture("blank-touch-clears-focus");
    checks.push(check);
    await touchPage.close();
    results.push({
      browser: name,
      version: browser.version(),
      ok: true,
      checks,
      screenshots,
    });
  } catch (error) {
    if (process.env.EVIDENCE_ARTIFACT_DIRECTORY)
      await inputPage.screenshot({
        path: `${process.env.EVIDENCE_ARTIFACT_DIRECTORY}/input-failure-${name}.png`,
      });
    results.push({
      browser: name,
      ok: false,
      check,
      error: String(error),
      tabObservations,
      touchObservation,
      nativeControlObservations,
      keyboardPointObservations,
      focusedCards: await inputPage
        .locator(
          '[data-testid="extract-pane"] [data-annotation-id][aria-current="true"]'
        )
        .evaluateAll((nodes) =>
          nodes.map((node) => node.getAttribute("data-annotation-id"))
        ),
    });
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify(results));
if (results.some((result) => !result.ok)) process.exitCode = 1;
