import { expect, test } from "@playwright/test";
import { actAs, seededUser } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

for (const path of ["/", "/history"]) {
  test(`${path} has no sideways scrolling on a phone`, async ({ page, request }) => {
    await actAs(page, (await seededUser(request, "demo_outdoor_maya")).id);
    await page.goto(path);
    await expect(page.locator("article, [data-event-row]").first()).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("a phone can reach every action on a card", async ({ page, request }) => {
  await actAs(page, (await seededUser(request, "demo_creative_lena")).id);
  await page.goto("/");

  const actions = page.getByTestId("recommendations").locator("article").first().locator("[data-event]");
  await expect(actions).toHaveCount(5);
  for (const button of await actions.all()) {
    const box = await button.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  }
});
