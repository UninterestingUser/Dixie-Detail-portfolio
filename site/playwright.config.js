// Browser tests of the booking flow against the fake API (tests/fake/api.mjs).
// One worker: the fake keeps state, and each test resets it.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  workers: 1,
  timeout: 60000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: "http://127.0.0.1:4321", trace: "retain-on-failure", timezoneId: "America/New_York" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] }, grep: /@phone/ },
  ],
  webServer: { command: "node tests/serve.mjs", url: "http://127.0.0.1:4321/book/", reuseExistingServer: !process.env.CI },
});
