import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["html", { outputFolder: "docs/qa/playwright-report", open: "never" }], ["line"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    colorScheme: "light",
    reducedMotion: "no-preference",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1024, height: 900 } } },
    { name: "mobile-chromium", use: { ...devices["iPhone 13"], viewport: { width: 375, height: 812 } } },
    { name: "small-mobile-chromium", use: { ...devices["Pixel 5"], viewport: { width: 320, height: 720 } } },
  ],
});
