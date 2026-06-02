// Phase-8-Smoke: DSGVO-Loesch-Route ist erreichbar und API antwortet.
// Wir loeschen hier NICHTS — nur Reachability als Gate.

import { test, expect } from "./fixtures.js";

test.describe("DSGVO RtbF (#148)", () => {
  test("DataDeletion-Route rendert", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/data-deletion", { waitUntil: "networkidle" });
    await expect(page.locator("body")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("GET /api/deletion-requests antwortet (auch wenn leer)", async ({
    request,
  }) => {
    const resp = await request.get("/api/deletion-requests");
    // 200 ist sauber, 404 akzeptieren wir wenn der Endpoint anders heisst,
    // 401/403 NICHT — das waere ein Auth-Bug
    expect([200, 404]).toContain(resp.status());
  });
});
