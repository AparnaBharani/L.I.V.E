"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useDemoUser } from "@/components/DemoUserProvider";
import { ExperienceActions, ExperienceMeta } from "@/components/ExperienceCard";
import { ErrorMessage, Loading } from "@/components/Status";
import { useActivity } from "@/components/useActivity";
import { api } from "@/lib/api";
import { EMPTY_STATE, eventProperties } from "@/lib/events";
import type { Experience } from "@/lib/types";

export default function ExperiencePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { user } = useDemoUser();
  const activity = useActivity(user?.id ?? null);
  const [experience, setExperience] = useState<Experience | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isInteger(id)) return;
    api.getExperience(id).then(setExperience).catch((e: Error) => setError(e.message));
  }, [id]);

  // Log one "view" per (user, experience) page visit. The ref guard matters because
  // React Strict Mode runs effects twice in development.
  const { record } = activity;
  const viewed = useRef<string | null>(null);
  useEffect(() => {
    if (!user || !experience) return;
    const key = `${user.id}:${experience.id}`;
    if (viewed.current === key) return;
    viewed.current = key;
    record({ event_type: "view", experience_id: experience.id, properties: eventProperties("detail_page") }).catch(() => {});
  }, [user, experience, record]);

  if (!Number.isInteger(id)) return <Shell><ErrorMessage message="Invalid experience id." /></Shell>;
  if (error) return <Shell><ErrorMessage message={error} /></Shell>;
  if (!experience) return <Shell><Loading what="experience" /></Shell>;

  return (
    <Shell>
      <h1 className="text-2xl font-bold">{experience.title}</h1>
      <div className="mt-2"><ExperienceMeta experience={experience} /></div>
      <p className="mt-4 max-w-2xl text-zinc-700">{experience.description}</p>
      <div className="mt-6">
        <ExperienceActions
          state={activity.states.get(experience.id) ?? EMPTY_STATE}
          disabled={!user}
          onEvent={(type) =>
            record({ event_type: type, experience_id: experience.id, properties: eventProperties("detail_page") })
          }
        />
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6">
      <Link href="/" className="text-sm text-zinc-500 hover:text-zinc-900">← Back to catalogue</Link>
      <div className="mt-4">{children}</div>
    </main>
  );
}
