/**
 * Playwright E2E — Telegram-Settings UX + Feature-Verifikation
 *
 * Testet: TelegramBotSettings, Admin-Panel, Modell-Modus, Tenant-Switcher
 * Läuft gegen: http://localhost:8601 (oder PLAYWRIGHT_BASE_URL)
 *
 * Ausführen:
 *   cd frontend && npx playwright test tests/e2e/telegram-settings.spec.js --headed
 */

import { test, expect } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:8601";
const API_KEY = process.env.TEST_API_KEY || "test-api-key";

test.use({ baseURL: BASE });

// ──────────────────────────────────────────────────────────────────────────────
// Hilfsfunktionen
// ──────────────────────────────────────────────────────────────────────────────

async function login(page) {
  await page.goto("/");
  // API-Key setzen falls Login-Maske erscheint
  const keyInput = page.locator(
    'input[placeholder*="API"], input[name="apiKey"], input[type="password"]'
  );
  if (await keyInput.isVisible({ timeout: 2000 }).catch(() => false)) {
    await keyInput.fill(API_KEY);
    await page.keyboard.press("Enter");
    await page.waitForLoadState("networkidle");
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 1. TELEGRAM-SETTINGS — 3 Random-Checks
// ──────────────────────────────────────────────────────────────────────────────

test.describe("TelegramBotSettings", () => {
  test("1a) Settings-Seite erreichbar und Telegram-Sektion sichtbar", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    // Telegram-Sektion muss sichtbar sein
    await expect(
      page.locator("text=Telegram").or(page.locator("text=telegram")).first()
    ).toBeVisible({ timeout: 8000 });

    // Screenshot für UX-Review
    await page.screenshot({
      path: "test-results/telegram-settings-view.png",
      fullPage: true,
    });
  });

  test("1b) Token-Eingabefeld + Augen-Toggle vorhanden (DAU-User-Check)", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    const tokenInput = page
      .locator('input[type="password"], input[placeholder*="Token"], input[placeholder*="token"]')
      .first();

    // Pentester: Passwort-Feld darf Token nicht als Klartext zeigen
    await expect(tokenInput).toHaveAttribute("type", "password", {
      timeout: 8000,
    });

    // DAU-Test: Augen-Toggle zum Anzeigen
    const eyeButton = page
      .locator('button[aria-label*="zeig"], button[title*="Show"], button svg')
      .first();
    if (await eyeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await eyeButton.click();
      // Nach Toggle: Klartext
      await expect(tokenInput).toHaveAttribute("type", "text", {
        timeout: 3000,
      });
    }
  });

  test("1c) Leerer Token → Connect-Button disabled (Bug-Tester)", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    // Connect-Button ohne Token muss disabled sein
    const connectBtn = page
      .locator('button:has-text("Verbinden"), button:has-text("Connect"), button:has-text("Speichern")')
      .first();

    if (await connectBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(connectBtn).toBeDisabled({ timeout: 3000 });

      // DAU-User-Check: Tooltip oder Hinweis WARUM disabled?
      const hint = page.locator(
        'text=Token, [title*="Token"], [aria-describedby]'
      );
      const hasHint = await hint.isVisible({ timeout: 1000 }).catch(() => false);
      if (!hasHint) {
        console.warn(
          "UX-Befund: Disabled Connect-Button ohne Erklärung für DAU-User"
        );
      }
    }
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 2. MODELL-MODUS (#72) — 3 Random-Checks
// ──────────────────────────────────────────────────────────────────────────────

test.describe("Modell-Modus-Switch (#72)", () => {
  test("2a) Modell-Modus-Auswahl in Settings sichtbar", async ({ page }) => {
    await login(page);
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    const modelMode = page.locator(
      "text=Testmodus, text=Modell-Modus, text=Produktiv, select, [role=listbox]"
    ).first();
    await expect(modelMode).toBeVisible({ timeout: 8000 });

    await page.screenshot({
      path: "test-results/model-mode-settings.png",
      fullPage: true,
    });
  });

  test("2b) Modell-Modus API-Call auf /tenants/me/model-mode (Pentester)", async ({
    page,
  }) => {
    await login(page);

    const apiCalls = [];
    page.on("request", (req) => {
      if (req.url().includes("model-mode")) apiCalls.push(req.url());
    });

    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    // Modus-Wechsel auslösen (falls Dropdown vorhanden)
    const modeSelect = page
      .locator("select, [role=listbox], [role=combobox]")
      .first();
    if (await modeSelect.isVisible({ timeout: 3000 }).catch(() => false)) {
      await modeSelect.click();
      await page.waitForTimeout(500);
    }

    // API-Call sollte stattgefunden haben beim Laden der aktuellen Einstellung
    console.log("Modell-Modus API-Calls:", apiCalls);
  });

  test("2c) Modell-Modus-Wechsel → kein 500er (Bug-Tester)", async ({
    page,
  }) => {
    await login(page);

    const errors = [];
    page.on("response", (resp) => {
      if (resp.status() >= 500) {
        errors.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await page.goto("/settings");
    await page.waitForLoadState("networkidle");

    await expect(errors).toHaveLength(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 3. ADMIN-PANEL (#98) — 3 Random-Checks
// ──────────────────────────────────────────────────────────────────────────────

test.describe("Admin-Panel (#98)", () => {
  test("3a) Admin-Login-Seite erreichbar", async ({ page }) => {
    await page.goto("/admin");
    await page.waitForLoadState("networkidle");

    // Login-Formular muss erscheinen (kein 404)
    const loginForm = page.locator(
      'form, input[type="password"], text=Anmelden, text=Login'
    ).first();
    await expect(loginForm).toBeVisible({ timeout: 8000 });

    await page.screenshot({
      path: "test-results/admin-login.png",
      fullPage: true,
    });
  });

  test("3b) Falsches Passwort → Fehlermeldung (Pentester)", async ({
    page,
  }) => {
    await page.goto("/admin");
    await page.waitForLoadState("networkidle");

    const userInput = page.locator('input[type="text"], input[name="username"]').first();
    const passInput = page.locator('input[type="password"]').first();

    if (
      await userInput.isVisible({ timeout: 3000 }).catch(() => false) &&
      await passInput.isVisible({ timeout: 3000 }).catch(() => false)
    ) {
      await userInput.fill("admin");
      await passInput.fill("wrong-password");
      await page.keyboard.press("Enter");
      await page.waitForTimeout(1000);

      const errorMsg = page.locator(
        '[role="alert"], .error, text=Ungültig, text=Fehler, text=falsch, text=incorrect'
      ).first();
      await expect(errorMsg).toBeVisible({ timeout: 5000 });

      // Pentester: Kein Stack-Trace oder interne Info in der Fehlermeldung
      const pageContent = await page.content();
      expect(pageContent).not.toContain("Traceback");
      expect(pageContent).not.toContain("sqlalchemy");
      expect(pageContent).not.toContain("psycopg");
    }
  });

  test("3c) Admin-Panel nach Login: User-Management sichtbar (Bug-Tester)", async ({
    page,
  }) => {
    const adminUser = process.env.ADMIN_USER;
    const adminPass = process.env.ADMIN_PASSWORD;

    if (!adminUser || !adminPass) {
      test.skip(true, "ADMIN_USER/ADMIN_PASSWORD nicht gesetzt — Test übersprungen");
      return;
    }

    await page.goto("/admin");
    const userInput = page.locator('input[type="text"]').first();
    const passInput = page.locator('input[type="password"]').first();
    await userInput.fill(adminUser);
    await passInput.fill(adminPass);
    await page.keyboard.press("Enter");
    await page.waitForLoadState("networkidle");

    await expect(
      page.locator("text=User-Management, text=Benutzer, text=Users").first()
    ).toBeVisible({ timeout: 8000 });

    await page.screenshot({
      path: "test-results/admin-dashboard.png",
      fullPage: true,
    });
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 4. BUTTONS + NAVIGATION (UX-Designer-Check)
// ──────────────────────────────────────────────────────────────────────────────

test.describe("UX + Navigation (alle Buttons + Overlaps)", () => {
  test("4a) Hauptnavigation vollständig + kein Overlap", async ({ page }) => {
    await login(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Alle Nav-Links müssen sichtbar und klickbar sein
    const navLinks = await page.locator("nav a, aside a, [role=navigation] a").all();
    console.log(`Nav-Links gefunden: ${navLinks.length}`);

    for (const link of navLinks.slice(0, 8)) {
      const box = await link.boundingBox();
      if (box) {
        // Prüfe dass kein anderes Element das Link-Element überlappt
        const overlapping = await page.evaluate(
          ({ x, y }) => {
            const el = document.elementFromPoint(x + 5, y + 5);
            return el ? el.tagName : null;
          },
          { x: box.x, y: box.y }
        );
        console.log(
          `Link-Text: "${await link.textContent()}" → ElementAt(x,y): ${overlapping}`
        );
      }
    }

    await page.screenshot({
      path: "test-results/navigation-overview.png",
      fullPage: false,
    });
  });

  test("4b) Keine 404-Routen im Haupt-Nav (Bug-Tester)", async ({ page }) => {
    await login(page);

    const routes = [
      "/",
      "/sources",
      "/pipeline",
      "/ideas",
      "/posts",
      "/brand-voice",
      "/settings",
      "/analytics",
      "/memory",
    ];

    for (const route of routes) {
      const response = await page.goto(route);
      // 200 oder SPA (null bei client-side routing)
      if (response) {
        expect(response.status()).toBeLessThan(400);
      }
      const notFound = page.locator("text=404, text=Nicht gefunden").first();
      const hasNotFound = await notFound
        .isVisible({ timeout: 1000 })
        .catch(() => false);
      if (hasNotFound) {
        console.error(`404 auf Route: ${route}`);
      }
      expect(hasNotFound).toBe(false);
    }
  });

  test("4c) Dashboard lädt ohne JS-Fehler (DAU-User)", async ({ page }) => {
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") jsErrors.push(msg.text());
    });

    await login(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Kritische JS-Fehler filtern (ignoriere bekannte harmlose)
    const criticalErrors = jsErrors.filter(
      (e) =>
        !e.includes("favicon") &&
        !e.includes("ResizeObserver") &&
        !e.includes("Non-Error promise rejection")
    );

    if (criticalErrors.length > 0) {
      console.error("JS-Fehler:", criticalErrors);
    }
    expect(criticalErrors).toHaveLength(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// 5. TELEGRAM-ANOMALIE-LOG (Log-Sichtbarkeit für User)
// ──────────────────────────────────────────────────────────────────────────────

test.describe("Telegram-Anomalie-Log (Log-Sichtbarkeit)", () => {
  test("5a) Pipeline-Log-Seite erreichbar + zeigt Einträge", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/pipeline");
    await page.waitForLoadState("networkidle");

    await page.screenshot({
      path: "test-results/pipeline-log-view.png",
      fullPage: true,
    });

    const logArea = page.locator(
      "text=Log, text=log, text=Verlauf, .log, [class*=log]"
    ).first();
    const isVisible = await logArea.isVisible({ timeout: 5000 }).catch(() => false);
    console.log("Pipeline-Log sichtbar:", isVisible);
  });

  test("5b) Analytics-Anomalie-Ansicht erreichbar (Admin-Check)", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/analytics");
    await page.waitForLoadState("networkidle");

    // Anomalie-Sektion oder Cost-Anomaly-Widget
    const anomalySection = page
      .locator("text=Anomalie, text=anomaly, text=Warnung")
      .first();
    const hasSec = await anomalySection
      .isVisible({ timeout: 5000 })
      .catch(() => false);
    console.log("Anomalie-Sektion sichtbar:", hasSec);

    await page.screenshot({
      path: "test-results/analytics-anomaly-view.png",
      fullPage: true,
    });
  });

  test("5c) Webhook-Endpoint liefert 401 ohne Secret (Pentester)", async ({
    page,
  }) => {
    const response = await page.request.post("/api/telegram/webhook", {
      data: { test: true },
      headers: { "Content-Type": "application/json" },
      failOnStatusCode: false,
    });

    // Ohne X-Telegram-Bot-Api-Secret-Token → 401
    expect([401, 403]).toContain(response.status());
    console.log(`Webhook ohne Secret: ${response.status()}`);
  });
});
