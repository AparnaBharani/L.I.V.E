import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-16 text-center">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="mt-2 text-sm text-zinc-600">This page does not exist.</p>
      <Link href="/" className="mt-4 inline-block text-sm underline">
        Back to experiences
      </Link>
    </main>
  );
}
