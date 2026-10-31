import { expect, test } from "@playwright/test";
import { actAs, createUser, firstExperience } from "./helpers";

// Failures are simulated at the network layer: deterministic, and nothing else is disturbed.
const EXPERIENCES = /:8000\/experiences\?/;
const RECOMMENDATIONS = /:8000\/users\/\d+\/recommendations/;
const INTERACTIONS = /:8000\/users\/\d+\/interactions/;

test.beforeEach(async ({ page, request }) => {
  await actAs(page, (await createUser(request)).id);
});

test("backend unreachable: the catalogue says so", async ({ page }) => {
  await page.route(EXPERIENCES, (route) => route.abort());
  await page.goto("/");
  await expect(page.getByRole("alert").first()).toContainText("Cannot reach the L.I.V.E backend");
});

test("server error: the API's message is shown", async ({ page }) => {
  await page.route(EXPERIENCES, (route) => route.fulfill({ status: 500, json: { detail: "Database unavailable" } }));
  await page.goto("/");
  await expect(page.getByRole("alert").first()).toContainText("Database unavailable");
});

test("empty catalogue: explains how to add data", async ({ page }) => {
  await page.route(EXPERIENCES, (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByText("No experiences yet")).toBeVisible();
});

test("recommendations failing does not take down the catalogue", async ({ page }) => {
  await page.route(RECOMMENDATIONS, (route) => route.abort());
  await page.goto("/");
  await expect(page.locator('[aria-labelledby="for-you"]').getByRole("alert")).toBeVisible();
  await expect(page.locator("article[data-experience-id]")).toHaveCount(42);
});

test("a rejected event is reported on the card", async ({ page, request }) => {
  const experience = await firstExperience(request);
  await page.goto(`/experiences/${experience.id}`);
  await expect(page.locator('[data-event="save"]')).toBeVisible();

  await page.route(INTERACTIONS, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 500, json: { detail: "Could not store event" } })
      : route.fallback(),
  );
  await page.locator('[data-event="save"]').click();

  await expect(page.getByText("Could not record event: Could not store event")).toBeVisible();
  await expect(page.locator('[data-event="save"]')).toHaveText("Save"); // state did not change
});

test("an unknown experience shows the API's 404 message", async ({ page }) => {
  await page.goto("/experiences/2147483647");
  await expect(page.getByText(/Experience \d+ not found/)).toBeVisible();
});
