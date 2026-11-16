import { defineConfig } from "@playwright/test";

// E2E for the web UI (docs/design-plan.md: "E2E: Playwright で Web UI").
// Data is layer 0 only (docs/test-data.md): the synthetic demo from kemocore.demo,
// prepared by e2e/serve_demo.py. Run `npm run build` first so kemo serve has the current UI.
const PORT = 8790;

export default defineConfig({
  testDir: "e2e",
  // One server holds one open project, so tests run one at a time.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    locale: "ja-JP",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: `uv run python web/e2e/serve_demo.py ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/info`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
