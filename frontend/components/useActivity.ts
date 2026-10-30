"use client";

// A user's current per-experience state, and a way to record new events.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { applyEvent, EMPTY_STATE, toStateMap, type ExperienceState } from "@/lib/events";
import type { Interaction, NewInteraction } from "@/lib/types";

interface Loaded {
  userId: number;
  states: Map<number, ExperienceState>;
}

const NO_STATES = new Map<number, ExperienceState>();

export function useActivity(userId: number | null) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<{ userId: number; message: string } | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;
    api
      .getInteractionState(userId)
      .then((rows) => !cancelled && setLoaded({ userId, states: toStateMap(rows) }))
      .catch((e: Error) => !cancelled && setError({ userId, message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  // Ignore data that belongs to a previously selected user.
  const current = loaded && loaded.userId === userId ? loaded : null;
  const loadError = error && error.userId === userId ? error.message : null;

  /** POST the event; on success, update the state locally so the UI responds without a refetch. */
  const record = useCallback(
    async (event: NewInteraction): Promise<Interaction> => {
      if (userId === null) throw new Error("No demo user selected");
      const created = await api.createInteraction(userId, event);
      const experienceId = created.experience_id;
      if (experienceId !== null) {
        setLoaded((prev) => {
          if (!prev || prev.userId !== userId) return prev;
          const states = new Map(prev.states);
          states.set(experienceId, applyEvent(states.get(experienceId) ?? EMPTY_STATE, created.event_type));
          return { userId, states };
        });
      }
      setVersion((v) => v + 1);
      return created;
    },
    [userId],
  );

  return { states: current?.states ?? NO_STATES, record, version, ready: current !== null, error: loadError };
}
