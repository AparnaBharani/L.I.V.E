"use client";

import { useState } from "react";
import { useDemoUser } from "@/components/DemoUserProvider";
import { ExperienceCard } from "@/components/ExperienceCard";
import { ForYou } from "@/components/ForYou";
import { SearchResults } from "@/components/SearchResults";
import { Empty, ErrorMessage, Loading } from "@/components/Status";
import { useActivity } from "@/components/useActivity";
import { useExperiences } from "@/components/useExperiences";
import { api } from "@/lib/api";
import { EMPTY_STATE, eventProperties, type ExperienceEvent } from "@/lib/events";
import type { SearchResponse } from "@/lib/types";

const EXAMPLE_SEARCHES = [
  "something relaxing under ₹400",
  "ceramics",
  "learn something new in two hours",
  "free things to do with friends",
];

export default function CataloguePage() {
  const { user } = useDemoUser();
  const { experiences, error, loading } = useExperiences();
  const activity = useActivity(user?.id ?? null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  async function runSearch(rawText: string) {
    const text = rawText.trim();
    if (!text) return;
    setQuery(text);
    setSearching(true);
    setSearchError(null);
    try {
      setResult(await api.search(text));
      // Analytics must not break search, so a failed event is ignored here.
      if (user) {
        activity
          .record({ event_type: "search", query_text: text, properties: eventProperties("catalogue_search") })
          .catch(() => {});
      }
    } catch (e) {
      setSearchError((e as Error).message);
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setQuery("");
    setResult(null);
    setSearchError(null);
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6">
      {!result && (
        <div className="mb-5">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Find something worth doing</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-600">
            L.I.V.E recommends real things to learn, make and try, and learns from what you actually do.
            Describe what you are in the mood for, in your own words.
          </p>
        </div>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          runSearch(query);
        }}
        className="flex flex-col gap-2 sm:flex-row"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Describe what you want, e.g. something relaxing under ₹500"
          className="w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm"
          aria-label="Search experiences"
          maxLength={300}
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="rounded bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </form>

      {!result && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs" data-testid="examples">
          <span className="text-zinc-500">Try:</span>
          {EXAMPLE_SEARCHES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => runSearch(example)}
              className="rounded-full border border-zinc-300 bg-white px-2.5 py-1 text-zinc-700 hover:border-zinc-900"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {activity.error && <div className="mt-4"><ErrorMessage message={`Could not load your activity: ${activity.error}`} /></div>}
      {searchError && <div className="mt-4"><ErrorMessage message={searchError} /></div>}

      {result ? (
        <div className="mt-6">
          <SearchResults
            key={result.query}
            result={result}
            states={activity.states}
            record={activity.record}
            userId={user?.id ?? null}
            onClear={clearSearch}
          />
        </div>
      ) : (
        <>
          {user && activity.ready && (
            <ForYou
              userId={user.id}
              refreshKey={activity.version}
              states={activity.states}
              record={activity.record}
            />
          )}

          <h2 className="mt-10 text-lg font-semibold">All experiences</h2>

          <section className="mt-3">
            {loading && <Loading what="experiences" />}
            {error && <ErrorMessage message={error} />}
            {experiences && experiences.length === 0 && (
              <Empty>No experiences yet. Run <code>python -m scripts.seed</code> in backend/.</Empty>
            )}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {experiences?.map((experience, index) => (
                <ExperienceCard
                  key={experience.id}
                  experience={experience}
                  state={activity.states.get(experience.id) ?? EMPTY_STATE}
                  disabled={!user}
                  onEvent={(type: ExperienceEvent) =>
                    activity.record({
                      event_type: type,
                      experience_id: experience.id,
                      properties: eventProperties("catalogue", index),
                    })
                  }
                />
              ))}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
