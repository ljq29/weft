import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:5173", headless: true },
  webServer: [
    {
      command: "uv run weft serve --no-browser",
      cwd: "..",
      url: "http://127.0.0.1:7788/health",
      env: {
        WEFT_CONFIG_DIR: ".test-reports/e2e-config",
        WEFT_DEV_ORIGIN: "http://127.0.0.1:5173",
      },
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "pnpm -C frontend dev --host 127.0.0.1",
      cwd: "..",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
