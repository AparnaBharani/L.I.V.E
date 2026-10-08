"use client";

import Link from "next/link";
import { useDemoUser } from "@/components/DemoUserProvider";
import { Empty, ErrorMessage, Loading } from "@/components/Status";
import { useActivity } from "@/components/useActivity";
import { useExperiences } from "@/components/useExperiences";
import { formatTimestamp } from "@/lib/format";

export default function HistoryPage() {
  const { user } = useDemoUser();
  const { interactions, loading, error } = useActivity(user?.id ?? null);
  const { experiences } = useExperiences();
  const titles = new Map((experiences ?? []).map((e) => [e.id, e.title]));

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6">
      <h1 className="text-2xl font-bold">Interaction history</h1>
      <p className="mt-1 text-sm text-zinc-600">
        The event log for <strong>{user?.username ?? "…"}</strong>, newest first, exactly as stored by{" "}
        <code>GET /users/{user?.id ?? "{id}"}/interactions</code> (latest 100).
      </p>

      <section className="mt-6">
        {!user && <Empty>Select a demo user in the header.</Empty>}
        {user && loading && <Loading what="history" />}
        {error && <ErrorMessage message={error} />}
        {interactions && interactions.length === 0 && (
          <Empty>No interactions yet: this is a cold-start user. Actions in the catalogue will appear here.</Empty>
        )}
        {interactions && interactions.length > 0 && (
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-300 text-xs uppercase text-zinc-500">
                <th className="py-2 pr-4">When</th>
                <th className="py-2 pr-4">Event</th>
                <th className="py-2 pr-4">Experience / query</th>
                <th className="py-2">Source</th>
              </tr>
            </thead>
            <tbody>
              {interactions.map((event) => (
                <tr key={event.id} className="border-b border-zinc-100" data-event-row={event.event_type}>
                  <td className="py-1.5 pr-4 whitespace-nowrap text-zinc-500">{formatTimestamp(event.occurred_at)}</td>
                  <td className="py-1.5 pr-4 font-mono">{event.event_type}</td>
                  <td className="py-1.5 pr-4">
                    {event.experience_id !== null ? (
                      <Link href={`/experiences/${event.experience_id}`} className="hover:underline">
                        {titles.get(event.experience_id) ?? `Experience ${event.experience_id}`}
                      </Link>
                    ) : (
                      <span className="italic">“{event.query_text}”</span>
                    )}
                  </td>
                  <td className="py-1.5 text-zinc-500">{String(event.properties?.source ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
