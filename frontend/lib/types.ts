// Mirrors the backend's Pydantic response schemas (backend/app/schemas.py).

export type EventType =
  | "view"
  | "click"
  | "save"
  | "unsave"
  | "like"
  | "unlike"
  | "dislike"
  | "search"
  | "complete"
  | "skip";

export interface Experience {
  id: number;
  title: string;
  description: string;
  category: string;
  difficulty: string;
  duration_minutes: number;
  cost: number;
  created_at: string;
}

export interface User {
  id: number;
  username: string;
  created_at: string;
}

export type EventProperties = Record<string, string | number | boolean>;

export interface Interaction {
  id: number;
  user_id: number;
  experience_id: number | null;
  event_type: EventType;
  query_text: string | null;
  properties: EventProperties | null;
  occurred_at: string;
}

// What the client is allowed to send (backend InteractionCreate). There is no
// user_id, id or occurred_at: the URL names the user, the server sets the rest.
// The union mirrors the backend rule: search has a query, everything else an experience.
export type NewInteraction =
  | { event_type: "search"; query_text: string; properties?: EventProperties }
  | {
      event_type: Exclude<EventType, "search">;
      experience_id: number;
      properties?: EventProperties;
    };
