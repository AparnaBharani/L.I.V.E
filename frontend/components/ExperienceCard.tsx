"use client";

import Link from "next/link";
import { useState } from "react";
import type { ExperienceEvent, ExperienceState } from "@/lib/events";
import { formatCost, formatDuration } from "@/lib/format";
import type { Experience } from "@/lib/types";

interface Props {
  experience: Experience;
  state: ExperienceState;
  /** Record an event for this experience. Rejects if the backend refuses it. */
  onEvent: (type: ExperienceEvent) => Promise<unknown>;
  disabled?: boolean;
  /** Extra content, e.g. recommendation reasons. */
  children?: React.ReactNode;
}

export function ExperienceMeta({ experience }: { experience: Experience }) {
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="rounded bg-zinc-900 px-2 py-0.5 text-white">{experience.category}</span>
      <span className="rounded bg-zinc-100 px-2 py-0.5">{experience.difficulty}</span>
      <span className="rounded bg-zinc-100 px-2 py-0.5">{formatDuration(experience.duration_minutes)}</span>
      <span className="rounded bg-zinc-100 px-2 py-0.5">{formatCost(experience.cost)}</span>
    </div>
  );
}

export function ExperienceActions({ state, onEvent, disabled }: Omit<Props, "experience" | "children">) {
  const [pending, setPending] = useState<ExperienceEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(type: ExperienceEvent) {
    setPending(type);
    setError(null);
    try {
      await onEvent(type);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(null);
    }
  }

  const buttons: { type: ExperienceEvent; label: string; active?: boolean }[] = [
    state.saved ? { type: "unsave", label: "Saved ✓", active: true } : { type: "save", label: "Save" },
    state.liked ? { type: "unlike", label: "Liked ✓", active: true } : { type: "like", label: "Like" },
    { type: "dislike", label: state.disliked ? "Disliked" : "Dislike", active: state.disliked },
    { type: "complete", label: state.completed ? "Done ✓" : "Mark done", active: state.completed },
    { type: "skip", label: "Not for me" },
  ];

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {buttons.map((b) => (
          <button
            key={b.type}
            type="button"
            data-event={b.type}
            disabled={disabled || pending !== null}
            onClick={() => send(b.type)}
            className={`rounded border px-2 py-1 text-xs disabled:opacity-50 ${
              b.active ? "border-zinc-900 bg-zinc-900 text-white" : "border-zinc-300 hover:border-zinc-900"
            }`}
          >
            {pending === b.type ? "…" : b.label}
          </button>
        ))}
      </div>
      {error && <p className="mt-1 text-xs text-red-600">Could not record event: {error}</p>}
    </div>
  );
}

export function ExperienceCard({ experience, state, onEvent, disabled, children }: Props) {
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4" data-experience-id={experience.id}>
      <div>
        <Link
          href={`/experiences/${experience.id}`}
          // A click on the title is a "click" event; the detail page then logs "view".
          onClick={() => {
            if (!disabled) onEvent("click").catch(() => {});
          }}
          className="font-semibold hover:underline"
        >
          {experience.title}
        </Link>
        <p className="mt-1 line-clamp-2 text-sm text-zinc-600">{experience.description}</p>
      </div>
      <ExperienceMeta experience={experience} />
      {children}
      <div className="mt-auto">
        <ExperienceActions state={state} onEvent={onEvent} disabled={disabled} />
      </div>
    </article>
  );
}
