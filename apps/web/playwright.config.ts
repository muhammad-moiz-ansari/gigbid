import { defineConfig, devices } from "@playwright/test";
import { randomUUID } from "node:crypto";
import path from "node:path";

const root = path.resolve(__dirname, "../..");
const runId = randomUUID();
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60000,
  expect: { timeout: 20000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: path.join(root, ".cache/phase6-browser-results"),
  reporter: [["list"], ["json", { outputFile: path.join(root, ".cache/phase6-browser.json") }]],
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined
  },
  webServer: [
    {
      command: `"${path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python")}" -m tests.e2e_server`,
      cwd: root, url: "http://127.0.0.1:8106/health", reuseExistingServer: false, timeout: 60000,
      env: { GIGBID_E2E_TEST_SERVER: "1", GIGBID_E2E_RUN_ID: runId }
    },
    {
      command: "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3100",
      cwd: __dirname, url: "http://127.0.0.1:3100", reuseExistingServer: false, timeout: 120000,
      env: { API_INTERNAL_URL: "http://127.0.0.1:8106", NEXT_TELEMETRY_DISABLED: "1", GIGBID_E2E_TEST_SERVER: "1" }
    }
  ]
});

