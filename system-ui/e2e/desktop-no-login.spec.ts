import { expect, test } from "@playwright/test";

test("browser deployment still requires user login", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "CVIS System UI" })).toBeVisible();
  await expect(page.getByText("Analyze Error Logs")).toHaveCount(0);
});

test("desktop webview opens dashboard with its local API key and no account login", async ({ page }) => {
  await page.addInitScript(() => {
    window.pywebview = {
      api: {
        get_api_key: async () => "local-desktop-test-key",
        quit_cvis: async () => ({ status: "shutting_down" }),
      },
    };
  });

  const apiRequests: Array<{ path: string; apiKey: string | undefined }> = [];
  await page.route("**/*", async (route) => {
    const request = route.request();
    const accept = request.headers()["accept"] ?? "";

    // Leave HTML, JavaScript, CSS, images, and other assets untouched.
    if (!accept.includes("application/json")) {
      await route.continue();
      return;
    }

    const path = new URL(request.url()).pathname;

    apiRequests.push({
      path,
      apiKey: request.headers()["x-api-key"],
    });

    const arrayPaths = new Set([
      "/actions/available",
      "/alerts/history",
      "/cognitive/predictions",
      "/cognitive/incidents",
      "/cognitive/notifications",
    ]);

    const body =
      path === "/desktop/settings"
        ? { available: true, configured: true, background_monitoring: false }
        : arrayPaths.has(path)
          ? []
          : {};

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto("/");

  await expect(page.getByText("Analyze Error Logs")).toBeVisible();
  await expect(page.getByRole("heading", { name: "CVIS System UI" })).toHaveCount(0);
  await expect.poll(() =>
    apiRequests.some((request) => request.path === "/os/status"),
  ).toBe(true);
  expect(apiRequests.every((request) => request.apiKey === "local-desktop-test-key")).toBe(true);
});
