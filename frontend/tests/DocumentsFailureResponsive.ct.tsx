import React from "react";
import { test, expect } from "./utils/coverage";
import { DocumentsFailureResponsiveTestWrapper } from "./DocumentsFailureResponsiveTestWrapper";

for (const width of [600, 768, 769, 1024]) {
  for (const view of ["grid", "list", "compact"] as const) {
    test(`${view} keeps failure and next step visible at width ${width}`, async ({
      mount,
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await mount(<DocumentsFailureResponsiveTestWrapper view={view} />);
      const failures = page.getByRole("status");
      await expect(failures).toHaveCount(2);
      for (const failure of await failures.all()) {
        await expect(failure.getByText("Processing failed")).toBeVisible();
        await expect(
          failure.getByText(/contact an administrator/i)
        ).toBeVisible();
        const box = await failure.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      }
      await expect(page.getByText(/^Processing(?:\.\.\.)?$/)).toHaveCount(0);
    });
  }
}
