import { expect, test } from "@playwright/test";
import { actAs, createUser, eventTypes } from "./helpers";

test("shows experience cards with their details", async ({ page, request }) => {
  await actAs(page, (await createUser(request)).id);
  await page.goto("/");

  const card = page.locator("article[data-experience-id]").last();
  await expect(card).toBeVisible();
  await expect(page.locator("article[data-experience-id]")).toHaveCount(48); // 6 recommended + 42
  await expect(card).toContainText(/beginner|intermediate|advanced/);
  await expect(card).toContainText(/Free|₹/);
});

test("opening an experience records one click, then one view", async ({ page, request }) => {
  const user = await createUser(request);
  await actAs(page, user.id);
  await page.goto("/");

  const link = page.locator("article[data-experience-id]").last().getByRole("link");
  const title = await link.textContent();
  await link.click();

  await expect(page.getByRole("heading", { level: 1, name: title! })).toBeVisible();
  await expect.poll(() => eventTypes(request, user.id)).toEqual(["view", "click"]);
});
