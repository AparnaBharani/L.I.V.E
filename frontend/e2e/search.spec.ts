import { expect, test, type Page } from "@playwright/test";
import { actAs, createUser, events, seededUser } from "./helpers";

const results = (page: Page) => page.locator('[aria-labelledby="search-results"] article');

async function search(page: Page, text: string) {
  await page.getByLabel("Search experiences").fill(text);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test.beforeEach(async ({ page, request }) => {
  await actAs(page, (await createUser(request)).id);
  await page.goto("/");
  await expect(page.locator("article[data-experience-id]").first()).toBeVisible();
});

test("finds an experience by meaning when no words are shared", async ({ page }) => {
  await search(page, "ceramics");
  await expect(page.locator('[aria-labelledby="search-results"]')).toHaveAttribute("data-mode", "hybrid");
  await expect(results(page).getByRole("link", { name: "Beginner pottery wheel class" })).toBeVisible();
});

test("a budget in the sentence is shown and enforced", async ({ page }) => {
  await search(page, "something relaxing under ₹400");

  await expect(page.getByTestId("understood")).toContainText("Up to ₹400");
  await expect(results(page).first()).toBeVisible();
  const prices = await results(page).evaluateAll((cards) =>
    cards.map((card) => (/Free/.test(card.textContent ?? "") ? 0 : Number(/₹([\d,]+)/.exec(card.textContent ?? "")?.[1].replace(",", "")))),
  );
  expect(Math.max(...prices)).toBeLessThanOrEqual(400);
});

test("constraints alone list what satisfies them", async ({ page }) => {
  await search(page, "free for beginners");
  await expect(page.getByTestId("understood")).toContainText("Free");
  await expect(page.getByTestId("understood")).toContainText("beginner");
  await expect(results(page).first()).toContainText("Fits your filters");
});

test("a search is recorded and clearing it restores the catalogue", async ({ page, request }) => {
  const userId = Number(await page.evaluate(() => window.localStorage.getItem("live.demoUserId")));
  await search(page, "pottery");
  await expect(results(page).first()).toBeVisible();

  await expect.poll(async () => (await events(request, userId))[0]?.query_text).toBe("pottery");

  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(page.getByRole("heading", { name: "All experiences" })).toBeVisible();
  await expect(page.getByLabel("Search experiences")).toHaveValue("");
});

test("acting on a result records where it came from", async ({ page, request }) => {
  const userId = Number(await page.evaluate(() => window.localStorage.getItem("live.demoUserId")));
  await search(page, "pottery");
  await results(page).first().locator('[data-event="save"]').click();

  await expect.poll(async () => (await events(request, userId))[0]?.properties).toEqual({ source: "search", position: 0 });
});

test("no results explains itself", async ({ page }) => {
  await search(page, "kubernetes cluster upgrade");
  await expect(page.getByText("Nothing matches")).toBeVisible();
});

test("a failed search shows an error and leaves the page usable", async ({ page }) => {
  await page.route(/:8000\/search/, (route) => route.fulfill({ status: 500, json: { detail: "Search failed" } }));
  await search(page, "pottery");
  await expect(page.getByRole("alert").filter({ hasText: "Search failed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "All experiences" })).toBeVisible();
});

test("without the model, search still answers by keyword and says so", async ({ page }) => {
  await page.route(/:8000\/search/, async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), mode: "keyword" } });
  });
  await search(page, "pottery");
  await expect(page.getByText("Matching by keywords only")).toBeVisible();
});

test("search results can be re-ranked for the user with grounded reasons", async ({ page, request }) => {
  const user = await seededUser(request, "demo_creative_lena");
  await actAs(page, user.id);
  await page.goto("/");
  await search(page, "something to make with my hands");
  await expect(results(page).first()).toBeVisible();
  const total = await results(page).count();

  await page.getByRole("button", { name: "Rank for me" }).click();

  await expect(page.getByText("Ordered for you")).toBeVisible();
  await expect(results(page).first()).toContainText("matches your search");
  expect(await results(page).count()).toBeLessThanOrEqual(total);
});
