"use client";

// DEMO ONLY: who "you" are is chosen from a dropdown and remembered in the browser.
// This is NOT authentication; anyone can act as any user. Real auth arrives in V8.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

const STORAGE_KEY = "live.demoUserId";

interface DemoUserContextValue {
  users: User[];
  user: User | null;
  setUserId: (id: number) => void;
  loading: boolean;
  error: string | null;
}

const DemoUserContext = createContext<DemoUserContextValue | null>(null);

function readStoredId(): number | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value ? Number(value) : null;
  } catch {
    return null;
  }
}

export function DemoUserProvider({ children }: { children: React.ReactNode }) {
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserIdState] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listUsers()
      .then((list) => {
        setUsers(list);
        const stored = readStoredId();
        setUserIdState(list.some((u) => u.id === stored) ? stored : (list[0]?.id ?? null));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const setUserId = useCallback((id: number) => {
    setUserIdState(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      // storage unavailable (private mode): selection just won't persist
    }
  }, []);

  const user = users.find((u) => u.id === userId) ?? null;

  return (
    <DemoUserContext.Provider value={{ users, user, setUserId, loading, error }}>
      {children}
    </DemoUserContext.Provider>
  );
}

export function useDemoUser(): DemoUserContextValue {
  const value = useContext(DemoUserContext);
  if (!value) throw new Error("useDemoUser must be used inside <DemoUserProvider>");
  return value;
}
