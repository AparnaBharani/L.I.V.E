import { expect, test, type Page } from "@playwright/test";
import { actAs, createUser, eventTypes, seededUser } from "./helpers";

const section = (page: Page) => page.locator('[aria-labelledby="for-you"]');
const cards = (page: Page) => page.getByTestId("recommendations").locator("article");

test("a new user gets labelled cold-start picks from several categories", async ({ page, request }) => {
  await actAs(page, (await createUser(request)).id);
  await page.goto("/");

  await expect(section(page)).toHaveAttribute("data-strategy", "cold_start");
  await expect(page.getByRole("heading", { name: "Popular picks to get you started" })).toBeVisible();
  await expect(cards(page)).toHaveCount(6);
  const categories = await cards(page).evaluateAll((a) => a.map((el) => el.getAttribute("data-category")));
  expect(new Set(categories).size).toBeGreaterThanOrEqual(4);
});

test("interacting closes the loop: event, new profile, new recommendations", async ({ page, request }) => {
  const user = await createUser(request);
  await actAs(page, user.id);
  await page.goto("/");

  const picked = cards(page).first();
  const id = await picked.getAttribute("data-experience-id");
  const category = await picked.getAttribute("data-category");
  await picked.locator('[data-event="save"]').click();

  await expect(section(page)).toHaveAttribute("data-strategy", "personalized");
  await expect(page.getByRole("heading", { name: "Recommended for you" })).toBeVisible();

  await page.locator(`article[data-experience-id="${id}"]`).first().locator('[data-event="complete"]').click();
  await expect.poll(() => eventTypes(request, user.id)).toEqual(["complete", "save"]);

  await expect(page.getByTestId("recommendations").locator(`article[data-experience-id="${id}"]`)).toHaveCount(0);
  await expect(cards(page).first()).toHaveAttribute("data-category", category!);
});

for (const [username, category] of [
  ["demo_outdoor_maya", "outdoors"],
  ["demo_creative_lena", "creative"],
] as const) {
  test(`${username} sees ${category} first, with a reason`, async ({ page, request }) => {
    await actAs(page, (await seededUser(request, username)).id);
    await page.goto("/");

    await expect(section(page)).toHaveAttribute("data-strategy", "personalized");
    await expect(cards(page).first()).toHaveAttribute("data-category", category);
    await expect(cards(page).first()).toContainText(`matches your interest in ${category}`);
  });
}
