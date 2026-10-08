"use client";

// V2 "For You": recommendations from GET /users/{id}/recommendations.
// Interacting with a recommended card records a normal V1 event (source "recommendations"),
// which changes the user's newest event id, which refetches the recommendations:
//   recommendation → interaction → new event → updated profile → new recommendation
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { EMPTY_STATE, eventProperties, type ExperienceEvent, type ExperienceState } from "@/lib/events";
import type { NewInteraction, RecommendationsResponse } from "@/lib/types";
import { ExperienceCard } from "./ExperienceCard";
import { ErrorMessage, Loading } from "./Status";

interface Props {
  userId: number;
  /** Id of the user's newest event; when it changes, recommendations are refreshed. */
  latestEventId: number | null;
  states: Map<number, ExperienceState>;
  record: (event: NewInteraction) => Promise<unknown>;
}

interface Loaded {
  key: string;
  data: RecommendationsResponse;
}

export function ForYou({ userId, latestEventId, states, record }: Props) {
  const key = `${userId}:${latestEventId}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getRecommendations(userId)
      .then((data) => !cancelled && setLoaded({ key, data }))
      .catch((e: Error) => !cancelled && setError({ key, message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [userId, key]);

  // Keep showing the previous list while a refresh for the same user is in flight.
  const data = loaded && loaded.key.startsWith(`${userId}:`) ? loaded.data : null;
  const loadError = error && error.key === key ? error.message : null;
  const coldStart = data?.strategy === "cold_start";

  return (
    <section className="mt-6" aria-labelledby="for-you" data-strategy={data?.strategy}>
      <h2 id="for-you" className="text-lg font-semibold">
        {coldStart ? "Popular picks to get you started" : "Recommended for you"}
      </h2>
      <p className="text-xs text-zinc-500">
        {coldStart
          ? "No activity yet, so these are ranked by popularity and freshness, not by your taste. Interact with anything to personalise them."
          : "Ranked by the V2 rule-based recommender from your saves, likes, completions, skips and views."}
      </p>
      <div className="mt-3">
        {loadError && <ErrorMessage message={loadError} />}
        {!data && !loadError && <Loading what="recommendations" />}
        {data && data.items.length === 0 && (
          <p className="text-sm text-zinc-500">Nothing left to recommend: you have done or dismissed everything.</p>
        )}
        {data && data.items.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="recommendations">
            {data.items.map((item) => (
              <ExperienceCard
                key={item.experience.id}
                experience={item.experience}
                state={states.get(item.experience.id) ?? EMPTY_STATE}
                onEvent={(type: ExperienceEvent) =>
                  record({
                    event_type: type,
                    experience_id: item.experience.id,
                    properties: { ...eventProperties("recommendations", item.rank - 1), strategy: data.strategy },
                  })
                }
              >
                <div className="rounded bg-zinc-50 p-2 text-xs text-zinc-600">
                  <div className="mb-1 font-mono text-zinc-500">
                    #{item.rank} · score {item.score.toFixed(2)}
                  </div>
                  <ul className="list-inside list-disc">
                    {item.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              </ExperienceCard>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
