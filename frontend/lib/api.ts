// The only place the frontend talks HTTP to the backend.
import type { Experience, Interaction, NewInteraction, RecommendationsResponse, User } from "./types";

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

export const api = {
  listUsers: () => request<User[]>("/users?limit=100"),
  listExperiences: () => request<Experience[]>("/experiences?limit=100"),
  getExperience: (id: number) => request<Experience>(`/experiences/${id}`),
  getRecommendations: (userId: number, limit = 6) =>
    request<RecommendationsResponse>(`/users/${userId}/recommendations?limit=${limit}`),
  listInteractions: (userId: number) =>
    request<Interaction[]>(`/users/${userId}/interactions?limit=100`),
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
