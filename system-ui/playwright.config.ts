import { defineConfig } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadEnv } from "vite";

const configDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(configDirectory, "..");
const localEnv = loadEnv("test", repositoryRoot, "");

for (const name of ["CVIS_ADMIN_USER", "CVIS_ADMIN_PASS"]) {
  if (!process.env[name] && localEnv[name]) {
    process.env[name] = localEnv[name];
  }
}

const localFrontendUrl = "http://127.0.0.1:5173";
const baseURL = process.env.BASE_URL ?? localFrontendUrl;
const useManagedFrontend = !process.env.BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  reporter: "list",
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
  },
  ...(useManagedFrontend && {
    webServer: {
      command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
      url: localFrontendUrl,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  }),
});
