"use client";

// A user's event log plus the state derived from it, and a way to add events.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { deriveState } from "@/lib/events";
import type { Interaction, NewInteraction } from "@/lib/types";

interface Loaded {
  userId: number;
  items: Interaction[];
}

export function useActivity(userId: number | null) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<{ userId: number; message: string } | null>(null);

  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;
    api
      .listInteractions(userId)
      .then((items) => !cancelled && setLoaded({ userId, items }))
      .catch((e: Error) => !cancelled && setError({ userId, message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  // Ignore data that belongs to a previously selected user.
  const interactions = loaded && loaded.userId === userId ? loaded.items : null;
  const loadError = error && error.userId === userId ? error.message : null;

  const states = useMemo(() => deriveState(interactions ?? []), [interactions]);

  /** POST the event; on success, prepend it so the UI updates without a refetch. */
  const record = useCallback(
    async (event: NewInteraction): Promise<Interaction> => {
      if (userId === null) throw new Error("No demo user selected");
      const created = await api.createInteraction(userId, event);
      setLoaded((prev) =>
        prev && prev.userId === userId ? { userId, items: [created, ...prev.items] } : prev,
      );
      return created;
    },
    [userId],
  );

  return { interactions, states, record, loading: interactions === null && !loadError, error: loadError };
}
