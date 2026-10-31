import { defineConfig, devices } from "@playwright/test";

const python = process.env.E2E_PYTHON ?? (process.platform === "win32" ? "venv\\Scripts\\python.exe" : "venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  // Tests share one server and database; each creates its own user, so they stay independent.
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    // Lets a machine without Playwright's own browser use an installed one, e.g. "chrome".
    channel: process.env.E2E_BROWSER_CHANNEL,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Recreates and seeds live_db_e2e, then serves the API (see the script for its safety rules).
      command: `${python} -m scripts.e2e_server`,
      cwd: "../backend",
      url: "http://127.0.0.1:8000/",
      timeout: 120_000,
      // Never attach to a running dev server: that one is connected to live_db.
      reuseExistingServer: false,
    },
    {
      command: "npm run build && npm run start",
      url: "http://localhost:3000",
      timeout: 180_000,
      reuseExistingServer: false,
    },
  ],
});
