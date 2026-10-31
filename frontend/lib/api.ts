// The only place the frontend talks HTTP to the backend.
import type {
  Experience,
  ExperienceStateRow,
  Interaction,
  NewInteraction,
  RecommendationsResponse,
  SearchResponse,
  User,
} from "./types";

// Inlined at build time by Next.js (NEXT_PUBLIC_ prefix). See frontend/.env.example.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// FastAPI errors are {"detail": "text"} (404/409) or {"detail": [{msg, loc}, ...]} (422).
function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the L.I.V.E backend at ${API_URL}. Is it running?`);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      describeDetail(body?.detail) ?? `Request failed with status ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

const MAX_PAGE_SIZE = 100;

/** Follow limit/offset until a short page, so a list is never silently cut off. */
async function fetchAllPages<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  for (let offset = 0; ; offset += MAX_PAGE_SIZE) {
    const page = await request<T[]>(`${path}?limit=${MAX_PAGE_SIZE}&offset=${offset}`);
    items.push(...page);
    if (page.length < MAX_PAGE_SIZE) return items;
  }
}

export const api = {
  listUsers: () => fetchAllPages<User>("/users"),
  listExperiences: () => fetchAllPages<Experience>("/experiences"),
  getExperience: (id: number) => request<Experience>(`/experiences/${id}`),
  search: (query: string, limit = 30) =>
    request<SearchResponse>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`),
  getRecommendations: (userId: number, limit = 6) =>
    request<RecommendationsResponse>(`/users/${userId}/recommendations?limit=${limit}`),
  listInteractions: (userId: number, limit: number, offset: number) =>
    request<Interaction[]>(`/users/${userId}/interactions?limit=${limit}&offset=${offset}`),
  getInteractionState: (userId: number) =>
    request<ExperienceStateRow[]>(`/users/${userId}/interactions/state`),
  createInteraction: (userId: number, event: NewInteraction) =>
    request<Interaction>(`/users/${userId}/interactions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event),
      // Lets the request finish even if the user navigates away (e.g. a click
      // that opens another page).
      keepalive: true,
    }),
};
