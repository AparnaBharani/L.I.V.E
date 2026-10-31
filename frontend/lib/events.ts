// Event tracking: turning UI actions into interaction events, and keeping the
// "what is currently saved/liked/..." state up to date as they happen.
import type { EventProperties, EventType, ExperienceStateRow } from "./types";

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

/**
 * Apply one new event to an experience's state, so the UI updates without a refetch.
 * The backend's recommender/state.py defines these rules; this must stay in step with it.
 */
export function applyEvent(state: ExperienceState, type: EventType): ExperienceState {
  switch (type) {
    case "save":
      return { ...state, saved: true, skipped: false };
    case "unsave":
      return { ...state, saved: false };
    case "like":
      return { ...state, liked: true, disliked: false, skipped: false };
    case "unlike":
      return { ...state, liked: false };
    case "dislike":
      return { ...state, disliked: true, liked: false };
    case "complete":
      return { ...state, completed: true, skipped: false };
    case "skip":
      return { ...state, skipped: true };
    default:
      return state; // view, click, search don't change state
  }
}

export function toStateMap(rows: ExperienceStateRow[]): Map<number, ExperienceState> {
  return new Map(rows.map(({ experience_id, ...state }) => [experience_id, state]));
}
