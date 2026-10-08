export function Loading({ what }: { what: string }) {
  return <p className="py-8 text-center text-sm text-zinc-500">Loading {what}…</p>;
}

export function ErrorMessage({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      {message}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500">{children}</p>;
}
