import { expect, test } from "@playwright/test";

test("verification fragment posts token and continues to sign-in", async ({ page }) => {
  const requests: unknown[] = [];
  await page.route("**/auth/verify-email", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, json: { message: "verified" } });
  });

  await page.goto("/#verify-email=sample-token");

  await expect(page.getByRole("heading", { name: "Email verification" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Your email is verified. You can now sign in.");
  expect(requests).toEqual([{ token: "sample-token" }]);
  await expect(page).toHaveURL(/\/$/);

  await page.getByRole("button", { name: "Continue to sign in" }).click();
  await expect(page.getByLabel("Email or admin username")).toBeVisible();
});

test("verification failure is shown and can return to sign-in", async ({ page }) => {
  await page.route("**/auth/verify-email", async (route) => {
    await route.fulfill({ status: 400, json: { detail: "invalid token" } });
  });

  await page.goto("/#verify-email=expired-token");

  await expect(page.getByRole("status")).toHaveText(
    "This verification link is invalid, expired, or already used. Request a new link from sign-in.",
  );
  await page.getByRole("button", { name: "Continue to sign in" }).click();
  await expect(page.getByLabel("Email or admin username")).toBeVisible();
});