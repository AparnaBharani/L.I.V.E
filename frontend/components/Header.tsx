"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useDemoUser } from "./DemoUserProvider";

const NAV = [
  { href: "/", label: "Catalogue" },
  { href: "/history", label: "My history" },
];

export function Header() {
  const { users, user, setUserId, loading, error } = useDemoUser();
  const pathname = usePathname();

  return (
    <header className="border-b border-zinc-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight">
          L.I.V.E
        </Link>
        <nav className="flex gap-3 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "font-semibold text-zinc-900" : "text-zinc-500 hover:text-zinc-900"}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <label htmlFor="demo-user" className="text-zinc-500">
            Demo user
          </label>
          {loading ? (
            <span className="text-zinc-400">loading…</span>
          ) : error ? (
            <span className="text-red-600">{error}</span>
          ) : (
            <select
              id="demo-user"
              className="rounded border border-zinc-300 px-2 py-1"
              value={user?.id ?? ""}
              onChange={(e) => setUserId(Number(e.target.value))}
            >
              {users.length === 0 && <option value="">no users (run the seed script)</option>}
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.username}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
      <p className="bg-amber-50 px-4 py-1 text-center text-xs text-amber-800">
        Demo mode: there is no login. You are acting as the selected demo user, and every action is
        recorded as their interaction event.
      </p>
    </header>
  );
}
