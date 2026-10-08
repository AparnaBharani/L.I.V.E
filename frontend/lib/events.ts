// Event tracking: turning UI actions into V1 interaction events, and turning the
// event log back into "what is currently saved/liked/...".
import type { EventProperties, EventType, Interaction } from "./types";

export type ExperienceEvent = Exclude<EventType, "search">;

/** Where an event came from, stored in properties for later analysis. */
export function eventProperties(source: string, position?: number): EventProperties {
  return position === undefined ? { source } : { source, position };
}

export interface ExperienceState {
  saved: boolean;
  liked: boolean;
  disliked: boolean;
  completed: boolean;
  skipped: boolean;
}

export const EMPTY_STATE: ExperienceState = {
  saved: false,
  liked: false,
  disliked: false,
  completed: false,
  skipped: false,
};

/** Apply one event to an experience's state. Same rules the backend log implies. */
export function applyEvent(state: ExperienceState, type: EventType): ExperienceState {
  switch (type) {
    case "save":
      return { ...state, saved: true };
    case "unsave":
      return { ...state, saved: false };
    case "like":
      return { ...state, liked: true, disliked: false };
    case "unlike":
      return { ...state, liked: false };
    case "dislike":
      return { ...state, disliked: true, liked: false };
    case "complete":
      return { ...state, completed: true };
    case "skip":
      return { ...state, skipped: true };
    default:
      return state; // view, click, search don't change state
  }
}

/** Replay an (unordered) event log into per-experience state. Latest event wins. */
export function deriveState(interactions: Interaction[]): Map<number, ExperienceState> {
  const ordered = [...interactions].sort(
    (a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.id - b.id,
  );
  const states = new Map<number, ExperienceState>();
  for (const event of ordered) {
    if (event.experience_id === null) continue;
    const current = states.get(event.experience_id) ?? EMPTY_STATE;
    states.set(event.experience_id, applyEvent(current, event.event_type));
  }
  return states;
}
