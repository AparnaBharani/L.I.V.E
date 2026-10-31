"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { type ExperienceEvent, EMPTY_STATE, eventProperties, type ExperienceState } from "@/lib/events";
import { formatCost, formatDuration } from "@/lib/format";
import type {
  NewInteraction,
  ParsedQuery,
  RecommendationsResponse,
  SearchHit,
  SearchResponse,
} from "@/lib/types";
import { ExperienceCard } from "./ExperienceCard";
import { Empty, ErrorMessage } from "./Status";

/** Show what the query was understood to mean, so a hidden filter is never a mystery. */
function understoodLabels(understood: ParsedQuery): string[] {
  const labels: string[] = [];
  if (understood.max_cost === 0) labels.push("Free");
  else if (understood.max_cost !== null) labels.push(`Up to ${formatCost(understood.max_cost)}`);
  if (understood.max_duration_minutes !== null) labels.push(`Up to ${formatDuration(understood.max_duration_minutes)}`);
  if (understood.difficulty) labels.push(understood.difficulty);
  if (understood.category) labels.push(understood.category);
  return labels;
}

function matchReason(hit: SearchHit): string {
  if (hit.keyword_rank !== null && hit.semantic_rank !== null) return "Matches your words and meaning";
  if (hit.keyword_rank !== null) return "Matches your words";
  if (hit.semantic_rank !== null) return "Similar in meaning";
  return "Fits your filters";
}

interface Props {
  result: SearchResponse;
  states: Map<number, ExperienceState>;
  record: (event: NewInteraction) => Promise<unknown>;
  userId: number | null;
  onClear: () => void;
}

export function SearchResults({ result, states, record, userId, onClear }: Props) {
  const labels = understoodLabels(result.understood);
  const [personal, setPersonal] = useState<RecommendationsResponse | null>(null);
  const [personalError, setPersonalError] = useState<string | null>(null);

  async function rankForMe() {
    if (userId === null) return;
    setPersonalError(null);
    try {
      setPersonal(await api.getRecommendations(userId, 30, result.query));
    } catch (e) {
      setPersonalError((e as Error).message);
    }
  }

  // Each card is the experience plus why it is here, whichever ranking is showing.
  const cards = personal
    ? personal.items.map((item) => ({ experience: item.experience, why: item.reasons.join(" · ") }))
    : result.items.map((hit) => ({ experience: hit.experience, why: matchReason(hit) }));

  return (
    <section aria-labelledby="search-results" data-mode={result.mode}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="search-results" className="text-lg font-semibold">
          {result.total} result{result.total === 1 ? "" : "s"} for “{result.query}”
        </h2>
        <button type="button" onClick={onClear} className="text-sm text-zinc-500 underline hover:text-zinc-900">
          Clear search
        </button>
        {userId !== null && result.total > 1 && !personal && (
          <button type="button" onClick={rankForMe} className="text-sm text-zinc-500 underline hover:text-zinc-900">
            Rank for me
          </button>
        )}
        {personal && <span className="text-sm text-zinc-500">Ordered for you</span>}
      </div>
      {labels.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs" data-testid="understood">
          <span className="text-zinc-500">Understood as:</span>
          {labels.map((label) => (
            <span key={label} className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900">
              {label}
            </span>
          ))}
        </div>
      )}
      {result.mode === "keyword" && (
        <p className="mt-2 text-xs text-zinc-500">Matching by keywords only: meaning-based search is unavailable right now.</p>
      )}
      {personalError && <div className="mt-2"><ErrorMessage message={personalError} /></div>}
      <div className="mt-4">
        {cards.length === 0 ? (
          <Empty>Nothing matches “{result.query}”. Try fewer constraints or different words.</Empty>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map(({ experience, why }, index) => (
              <ExperienceCard
                key={experience.id}
                experience={experience}
                state={states.get(experience.id) ?? EMPTY_STATE}
                disabled={userId === null}
                onEvent={(type: ExperienceEvent) =>
                  record({
                    event_type: type,
                    experience_id: experience.id,
                    properties: eventProperties(personal ? "personalised_search" : "search", index),
                  })
                }
              >
                <p className="text-xs text-zinc-500">{why}</p>
              </ExperienceCard>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
