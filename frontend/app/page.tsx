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

export default function CataloguePage() {
  const { user } = useDemoUser();
  const { experiences, error, loading } = useExperiences();
  const activity = useActivity(user?.id ?? null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  async function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text) return;
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
      <form onSubmit={submitSearch} className="flex flex-col gap-2 sm:flex-row">
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

          <h1 className="mt-10 text-2xl font-bold">All experiences</h1>
          <p className="mt-1 text-sm text-zinc-600">Things to learn, build, explore and try. Every action is logged as an event.</p>

          <section className="mt-6">
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
