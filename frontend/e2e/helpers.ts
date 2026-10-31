import { randomUUID } from "node:crypto";
import type { APIRequestContext, Page } from "@playwright/test";
import type { Experience, Interaction, User } from "../lib/types";

export const API_URL = "http://127.0.0.1:8000";

/** A brand-new user, so a test never depends on (or disturbs) anyone else's history. */
export async function createUser(request: APIRequestContext): Promise<User> {
  const response = await request.post(`${API_URL}/users`, {
    data: { username: `e2e_${randomUUID().slice(0, 12).replace("-", "")}` },
  });
  return response.json();
}

export async function seededUser(request: APIRequestContext, username: string): Promise<User> {
  const users: User[] = await (await request.get(`${API_URL}/users?limit=100`)).json();
  const user = users.find((u) => u.username === username);
  if (!user) throw new Error(`Seeded user ${username} not found`);
  return user;
}

export async function firstExperience(request: APIRequestContext): Promise<Experience> {
  const [experience]: Experience[] = await (await request.get(`${API_URL}/experiences?limit=1`)).json();
  return experience;
}

export async function events(request: APIRequestContext, userId: number): Promise<Interaction[]> {
  return (await request.get(`${API_URL}/users/${userId}/interactions`)).json();
}

/** Newest-first event types, the shape most tests assert on. */
export async function eventTypes(request: APIRequestContext, userId: number): Promise<string[]> {
  return (await events(request, userId)).map((e) => e.event_type);
}

/** Select the demo user before the app loads, the way a returning visitor would have it stored. */
export async function actAs(page: Page, userId: number): Promise<void> {
  await page.addInitScript((id) => window.localStorage.setItem("live.demoUserId", String(id)), userId);
}
