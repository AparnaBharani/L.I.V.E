"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Experience } from "@/lib/types";

export function useExperiences() {
  const [experiences, setExperiences] = useState<Experience[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listExperiences()
      .then(setExperiences)
      .catch((e: Error) => setError(e.message));
  }, []);

  return { experiences, error, loading: experiences === null && error === null };
}
