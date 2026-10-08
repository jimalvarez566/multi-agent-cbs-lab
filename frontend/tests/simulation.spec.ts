import { expect, test } from "@playwright/test";

test("solve, scrub, dynamically replan, inspect tree, and reset", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  expect((await page.request.get("/health")).status()).toBe(200);
  expect((await page.request.get("/docs")).status()).toBe(200);
  await expect(
    page.getByRole("heading", { name: "Every agent. One clear path." }),
  ).toBeVisible();
  const solve = page.waitForResponse((r) => r.url().endsWith("/api/solve"));
  await page.getByRole("button", { name: "Solve with CBS" }).click();
  const solved = await solve;
  expect(solved.status()).toBe(200);
  const initial = await solved.json();
  expect(initial.metrics.collisions).toBe(0);
  expect(initial.tree.some((node: { constraint?: { positive: boolean } }) => node.constraint?.positive === true)).toBe(true);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.getByRole("slider", { name: "Playback step" }).fill("2");
  const disruption = page.waitForResponse((r) =>
    r.url().endsWith("/api/adversary/disrupt"),
  );
  await page.getByRole("button", { name: "Run Dynamic Bottleneck" }).click();
  const disrupted = await disruption;
  expect(disrupted.status()).toBe(200);
  const data = await disrupted.json();
  expect(data.metrics.collisions).toBe(0);
  await expect(page.getByText(/Bottleneck at/)).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Run Dynamic Bottleneck" }),
  ).toBeDisabled();
  await page.getByRole("slider", { name: "Playback step" }).fill("5");
  await expect(
    page.getByRole("button", { name: "Run Dynamic Bottleneck" }),
  ).toBeEnabled();
  await page.locator(".tree-node summary").first().click();
  await expect(page.locator(".tree-node").first().locator("p")).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /Random Grid/ }).click();
  await expect(
    page.getByRole("button", { name: "Run Dynamic Bottleneck" }),
  ).toBeDisabled();
  expect(errors).toEqual([]);
});

test("mobile layout has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("img", { name: /grid with 3 agents/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-mobile.png",
    fullPage: true,
  });
});

// Reproduce a first-frame timestamp that predates playback initialization.
test("playback stays valid when the first frame timestamp moves backward", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const nativeFrame = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (callback) =>
      nativeFrame((timestamp) => callback(timestamp - 100));
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const response = page.waitForResponse((r) => r.url().endsWith("/api/solve"));
  await page.getByRole("button", { name: "Solve with CBS" }).click();
  expect((await response).status()).toBe(200);
  await expect
    .poll(async () =>
      Number(
        await page.getByRole("slider", { name: "Playback step" }).inputValue(),
      ),
    )
    .toBeGreaterThan(0);
  expect(errors).toEqual([]);
});
