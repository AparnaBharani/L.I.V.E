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

// GET /users/{id}/interactions/state: computed by the backend from the whole event log.
export interface ExperienceStateRow {
  experience_id: number;
  saved: boolean;
  liked: boolean;
  disliked: boolean;
  completed: boolean;
  skipped: boolean;
}

// GET /search
export interface ParsedQuery {
  text: string;
  categories: string[];
  category: string | null;
  difficulty: string | null;
  max_cost: number | null;
  max_duration_minutes: number | null;
}

export interface SearchHit {
  score: number;
  keyword_rank: number | null;
  semantic_rank: number | null;
  category_hint: boolean;
  experience: Experience;
}

export interface SearchResponse {
  query: string;
  mode: "hybrid" | "keyword" | "browse";
  understood: ParsedQuery;
  total: number;
  items: SearchHit[];
}

// V2: GET /users/{id}/recommendations
export interface RecommendationItem {
  rank: number;
  score: number; // after diversity adjustment; sets the order
  relevance: number; // weighted feature score before diversity
  reasons: string[];
  features: Record<string, number>;
  experience: Experience;
}

export interface RecommendationsResponse {
  user_id: number;
  strategy: "personalized" | "cold_start";
  generated_at: string;
  candidate_count: number;
  items: RecommendationItem[];
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
