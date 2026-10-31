import { expect, test } from "@playwright/test";
import { actAs, createUser, events, eventTypes, firstExperience, seededUser } from "./helpers";

test("save, like and complete update the buttons and reach the history", async ({ page, request }) => {
  const user = await createUser(request);
  const experience = await firstExperience(request);
  await actAs(page, user.id);
  await page.goto(`/experiences/${experience.id}`);
  await expect.poll(() => eventTypes(request, user.id)).toEqual(["view"]);

  await page.locator('[data-event="save"]').click();
  await expect(page.locator('[data-event="unsave"]')).toHaveText("Saved ✓");
  await page.locator('[data-event="like"]').click();
  await expect(page.locator('[data-event="unlike"]')).toHaveText("Liked ✓");
  await page.locator('[data-event="complete"]').click();
  await expect(page.locator('[data-event="complete"]')).toHaveText("Done ✓");

  await page.getByRole("link", { name: "My history" }).click();
  await expect(page.locator("[data-event-row]")).toHaveCount(4);
  const rows = await page.locator("[data-event-row]").evaluateAll((r) => r.map((el) => el.getAttribute("data-event-row")));
  expect(rows).toEqual(["complete", "like", "save", "view"]);
  await expect(page.locator("[data-event-row]").first()).toContainText(experience.title);
});

test("unsave and unlike are recorded as reversal events", async ({ page, request }) => {
  const user = await createUser(request);
  const experience = await firstExperience(request);
  await actAs(page, user.id);
  await page.goto(`/experiences/${experience.id}`);

  await page.locator('[data-event="save"]').click();
  await page.locator('[data-event="unsave"]').click();
  await expect(page.locator('[data-event="save"]')).toHaveText("Save");
  await page.locator('[data-event="like"]').click();
  await page.locator('[data-event="unlike"]').click();
  await expect(page.locator('[data-event="like"]')).toHaveText("Like");

  await expect.poll(() => eventTypes(request, user.id)).toEqual(["unlike", "like", "unsave", "save", "view"]);
});

test("saved state survives a page reload", async ({ page, request }) => {
  const user = await createUser(request);
  const experience = await firstExperience(request);
  await actAs(page, user.id);
  await page.goto(`/experiences/${experience.id}`);

  await page.locator('[data-event="save"]').click();
  await expect(page.locator('[data-event="unsave"]')).toBeVisible();
  await page.reload();
  await expect(page.locator('[data-event="unsave"]')).toBeVisible();
});

test("events carry where they came from and never a client-chosen identity", async ({ page, request }) => {
  const user = await createUser(request);
  const experience = await firstExperience(request);
  await actAs(page, user.id);

  const sent = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/interactions"));
  await page.goto(`/experiences/${experience.id}`);
  const body = (await sent).postDataJSON();

  expect(Object.keys(body).sort()).toEqual(["event_type", "experience_id", "properties"]);
  await expect.poll(async () => (await events(request, user.id))[0]?.properties).toEqual({ source: "detail_page" });
});

test("switching demo users shows separate histories", async ({ page, request }) => {
  const [first, second] = [await createUser(request), await createUser(request)];
  const experience = await firstExperience(request);
  await actAs(page, first.id);
  await page.goto(`/experiences/${experience.id}`);
  await page.locator('[data-event="save"]').click();
  await expect(page.locator('[data-event="unsave"]')).toBeVisible();

  await page.goto("/history");
  await expect(page.locator("[data-event-row]")).toHaveCount(2);

  await page.locator("#demo-user").selectOption(String(second.id));
  await expect(page.getByText("cold-start user")).toBeVisible();
  await expect(page.locator("[data-event-row]")).toHaveCount(0);
});

test("a seeded cold-start user has an empty history", async ({ page, request }) => {
  await actAs(page, (await seededUser(request, "demo_coldstart_ella")).id);
  await page.goto("/history");
  await expect(page.getByText("cold-start user")).toBeVisible();
});
