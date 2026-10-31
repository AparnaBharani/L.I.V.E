"use client";

import { type ExperienceEvent, EMPTY_STATE, eventProperties, type ExperienceState } from "@/lib/events";
import { formatCost, formatDuration } from "@/lib/format";
import type { NewInteraction, ParsedQuery, SearchHit, SearchResponse } from "@/lib/types";
import { ExperienceCard } from "./ExperienceCard";
import { Empty } from "./Status";

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
  disabled: boolean;
  onClear: () => void;
}

export function SearchResults({ result, states, record, disabled, onClear }: Props) {
  const labels = understoodLabels(result.understood);

  return (
    <section aria-labelledby="search-results" data-mode={result.mode}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="search-results" className="text-lg font-semibold">
          {result.total} result{result.total === 1 ? "" : "s"} for “{result.query}”
        </h2>
        <button type="button" onClick={onClear} className="text-sm text-zinc-500 underline hover:text-zinc-900">
          Clear search
        </button>
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
      <div className="mt-4">
        {result.items.length === 0 ? (
          <Empty>Nothing matches “{result.query}”. Try fewer constraints or different words.</Empty>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {result.items.map((hit, index) => (
              <ExperienceCard
                key={hit.experience.id}
                experience={hit.experience}
                state={states.get(hit.experience.id) ?? EMPTY_STATE}
                disabled={disabled}
                onEvent={(type: ExperienceEvent) =>
                  record({
                    event_type: type,
                    experience_id: hit.experience.id,
                    properties: eventProperties("search", index),
                  })
                }
              >
                <p className="text-xs text-zinc-500">{matchReason(hit)}</p>
              </ExperienceCard>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
