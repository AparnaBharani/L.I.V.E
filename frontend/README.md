# L.I.V.E frontend

Next.js, React, TypeScript and Tailwind CSS. See the [project README](../README.md) for setup and
architecture.

```powershell
npm install
npm run dev        # http://localhost:3000 (needs the backend on port 8000)
npm run lint
npx tsc --noEmit
npm run build
npm run test:e2e   # stop your dev servers first
```

- `app/`: pages
- `components/`: UI and data hooks
- `lib/`: the API client, event helpers and shared types
- `e2e/`: Playwright browser tests
