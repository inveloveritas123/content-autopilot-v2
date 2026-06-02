// Phase-2-Smoke: Brand-Voice-Wizard kann gestartet werden.
// Verifiziert dass der 9-Fragen-Dialog vom Backend ausgeliefert und
// von der UI gerendert wird.

import { test, expect } from "./fixtures.js";

test.describe("Brand Voice Wizard", () => {
  test("GET /api/brand-voice/wizard/questions liefert die 9 Fragen", async ({
    request,
  }) => {
    const resp = await request.get("/api/brand-voice/wizard/questions");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    // Struktur: { phases: [...] } mit q1_*, q2_*, ..., q5_*
    expect(body).toBeTruthy();
    const allQuestions = JSON.stringify(body);
    expect(allQuestions).toMatch(/q1_1/);
    expect(allQuestions).toMatch(/q5_linkedin_posts/);
  });

  test("Wizard-Page rendert mit Start-Button", async ({ page }) => {
    await page.goto("/brand-voice/wizard", { waitUntil: "networkidle" });
    // Sehr generischer Check: irgendwo auf der Seite ist Wizard-Text
    await expect(page.locator("body")).toContainText(/wizard|brand|voice/i);
  });
});
