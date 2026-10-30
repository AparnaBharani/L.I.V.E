import { expect, test } from "@playwright/test";
import { actAs, createUser, eventTypes, events } from "./helpers";

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

test("keyword filter narrows the list and records a search", async ({ page, request }) => {
  const user = await createUser(request);
  await actAs(page, user.id);
  await page.goto("/");

  await page.getByLabel("Search experiences").fill("pottery");
  await expect(page.getByRole("link", { name: "Beginner pottery wheel class" }).last()).toBeVisible();
  await expect(page.locator("article[data-experience-id]")).not.toHaveCount(48);

  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText('Search "pottery" recorded.')).toBeVisible();

  const [latest] = await events(request, user.id);
  expect(latest).toMatchObject({ event_type: "search", query_text: "pottery", experience_id: null });
});

test("a filter with no matches explains itself", async ({ page, request }) => {
  await actAs(page, (await createUser(request)).id);
  await page.goto("/");

  await page.getByLabel("Search experiences").fill("zzzz-no-such-thing");
  await expect(page.getByText("Nothing matches")).toBeVisible();
});
