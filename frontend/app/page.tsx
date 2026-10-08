"use client";

import { useMemo, useState } from "react";
import { useDemoUser } from "@/components/DemoUserProvider";
import { ExperienceCard } from "@/components/ExperienceCard";
import { Empty, ErrorMessage, Loading } from "@/components/Status";
import { useActivity } from "@/components/useActivity";
import { useExperiences } from "@/components/useExperiences";
import { EMPTY_STATE, eventProperties, type ExperienceEvent } from "@/lib/events";

export default function CataloguePage() {
  const { user } = useDemoUser();
  const { experiences, error, loading } = useExperiences();
  const activity = useActivity(user?.id ?? null);
  const [query, setQuery] = useState("");
  const [searchNote, setSearchNote] = useState<string | null>(null);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!experiences || !q) return experiences ?? [];
    return experiences.filter((e) =>
      [e.title, e.description, e.category].some((field) => field.toLowerCase().includes(q)),
    );
  }, [experiences, query]);

  async function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || !user) return;
    try {
      await activity.record({ event_type: "search", query_text: text, properties: eventProperties("catalogue_search") });
      setSearchNote(`Search "${text}" recorded.`);
    } catch (e) {
      setSearchNote(`Search not recorded: ${(e as Error).message}`);
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6">
      <h1 className="text-2xl font-bold">Experiences</h1>
      <p className="mt-1 text-sm text-zinc-600">Things to learn, build, explore and try. Every action below is logged as an event.</p>

      <form onSubmit={submitSearch} className="mt-4 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by keyword, e.g. pottery, hike, yoga"
          className="w-full max-w-md rounded border border-zinc-300 px-3 py-1.5 text-sm"
          aria-label="Search experiences"
        />
        <button type="submit" disabled={!user || !query.trim()} className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          Search
        </button>
      </form>
      {searchNote && <p className="mt-1 text-xs text-zinc-500">{searchNote}</p>}

      <section className="mt-6">
        {loading && <Loading what="experiences" />}
        {error && <ErrorMessage message={error} />}
        {experiences && experiences.length === 0 && (
          <Empty>No experiences yet. Run <code>python -m scripts.seed</code> in backend/.</Empty>
        )}
        {experiences && experiences.length > 0 && visible.length === 0 && <Empty>Nothing matches “{query}”.</Empty>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((experience, index) => (
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
    </main>
  );
}
