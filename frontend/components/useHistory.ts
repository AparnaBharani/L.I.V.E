"use client";

// One user's event log, a page at a time, newest first.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Interaction } from "@/lib/types";

const PAGE_SIZE = 50;

interface Loaded {
  userId: number;
  items: Interaction[];
  hasMore: boolean;
}

export function useHistory(userId: number | null) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<{ userId: number; message: string } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;
    api
      .listInteractions(userId, PAGE_SIZE, 0)
      .then((items) => !cancelled && setLoaded({ userId, items, hasMore: items.length === PAGE_SIZE }))
      .catch((e: Error) => !cancelled && setError({ userId, message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const current = loaded && loaded.userId === userId ? loaded : null;
  const loadError = error && error.userId === userId ? error.message : null;

  const loadMore = useCallback(async () => {
    if (!current) return;
    setLoadingMore(true);
    try {
      const page = await api.listInteractions(current.userId, PAGE_SIZE, current.items.length);
      setLoaded({
        userId: current.userId,
        items: [...current.items, ...page],
        hasMore: page.length === PAGE_SIZE,
      });
    } catch (e) {
      setError({ userId: current.userId, message: (e as Error).message });
    } finally {
      setLoadingMore(false);
    }
  }, [current]);

  return {
    interactions: current?.items ?? null,
    hasMore: current?.hasMore ?? false,
    loadMore,
    loadingMore,
    loading: current === null && !loadError,
    error: loadError,
  };
}
