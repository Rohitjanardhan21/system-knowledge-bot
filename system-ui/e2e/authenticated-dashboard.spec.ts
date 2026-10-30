import { expect, test } from "@playwright/test";

declare const process: {
  env: Record<string, string | undefined>;
};

test("login loads authenticated telemetry and alerts", async ({ page }) => {
  const username = process.env.CVIS_ADMIN_USER;
  const password = process.env.CVIS_ADMIN_PASS;
  if (!username || !password) {
    throw new Error("CVIS_ADMIN_USER and CVIS_ADMIN_PASS are required for this test");
  }

  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "CVIS System UI" })).toBeVisible();
  await page.getByLabel("Email or admin username").fill(username);
  await page.getByLabel("Password").fill(password);

  const loginResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/auth/login" && response.request().method() === "POST";
  });
  const telemetryResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/os/status" && response.request().method() === "GET";
  }).catch(() => null);
  const alertsResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/alerts/history" && response.request().method() === "GET";
  }).catch(() => null);

  await page.getByRole("button", { name: "LOGIN" }).click();

  const login = await loginResponse;
  expect(
    login.status(),
    "Login was rejected. Verify the test credentials match those loaded by the backend container.",
  ).toBe(200);

  const telemetry = await telemetryResponse;
  const alerts = await alertsResponse;
  expect(telemetry?.status()).toBe(200);
  expect(alerts?.status()).toBe(200);
  await expect(page.getByText("Authentication required")).toHaveCount(0);
  expect(pageErrors).toEqual([]);

  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("heading", { name: "CVIS System UI" })).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
});
