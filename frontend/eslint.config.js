// ESLint Flat Config (ESLint 9+)
// Lokal: cd frontend && npm run lint
// Auto-Fix:  npm run lint:fix

import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default [
  { ignores: ['dist', 'node_modules', 'coverage', 'build'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // PascalCase vars (React components) are used in JSX but not detected without
      // eslint-plugin-react/jsx-uses-vars — exclude them from unused-vars check.
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_|^[A-Z]' }],
      // allowEmptyCatch: leere catch-Blöcke sind in UI-fire-and-forget-Aktionen
      // absichtlich — Fehler werden still ignoriert ohne die UI zu unterbrechen.
      // Das Pattern ist im gesamten Codebase konsistent eingesetzt.
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      // Design-Token-Gate (Redesign 2026-08-14, Schicht 2 aus
      // docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md): Ohne erzwingenden Mechanismus
      // verrottet ein Token-System nachweislich zurück (Vorzustand: 55/70 Dateien mit
      // Hex-Werten trotz vorhandenem tailwind.config.js-System). Bewusst 'warn', nicht
      // 'error' — der Bestand (Migrationswelle D6, noch offen) wird NICHT sofort
      // scharf geschaltet, sonst bricht `--max-warnings` den ganzen Build an
      // unmigrierten Altdateien. Auf 'error' heben, sobald D6 abgeschlossen ist.
      // Baseline bei Einführung (2026-08-14): 143 Hex-Fundstellen, eingefroren in
      // package.json `lint`-Script (--max-warnings N). Diese Zahl darf nur SINKEN
      // (jede migrierte Komponente senkt sie), nie angehoben werden um grün zu wirken.
      //
      // Gate-Fix (2026-08-14, nach Hub-Rückmeldung zu agy-Tranche 2): die erste
      // Fassung matchte JEDES Literal, dessen kompletter String-Wert dem
      // Hex-Zeichenmuster entsprach — unabhängig vom Kontext. Zwei belegte
      // Fehlalarme: '#146' (Issue-Nummer in einem Text-String,
      // LLMAnalytics.jsx) und '#B2B' (Hashtag-String, Posts.jsx — 'B2B' ist
      // zufällig gültiges Hex). Fix: der Selektor prüft jetzt zusätzlich, dass
      // das Literal an einer FARBWERT-TRAGENDEN Stelle steht (JSX-Attribut
      // color/fill/stroke/backgroundColor/borderColor o.ä., oder eine
      // entsprechende Objekt-Property in einem style={{}}-Ausdruck) statt nur
      // auf das Zeichenmuster allein zu vertrauen.
      'no-restricted-syntax': [
        'warn',
        {
          selector:
            "JSXAttribute[name.name=/^(color|fill|stroke|backgroundColor|borderColor|background|bg)$/i] Literal[value=/^#([0-9a-fA-F]{3}){1,2}$/]",
          message:
            'Kein Roh-Hex-Farbwert im Component-Code — Tier-2-Token aus tailwind.config.js nutzen (status-*, primary-*, accent-*, surface-*, ink-*). Siehe docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md.',
        },
        {
          selector:
            "Property[key.name=/^(color|fill|stroke|backgroundColor|borderColor|background)$/i] > Literal[value=/^#([0-9a-fA-F]{3}){1,2}$/]",
          message:
            'Kein Roh-Hex-Farbwert im Component-Code — Tier-2-Token aus tailwind.config.js nutzen (status-*, primary-*, accent-*, surface-*, ink-*). Siehe docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md.',
        },
        // Erweiterung (2026-08-14, D6 Tailwind-Klassen-Migration): rohe
        // Tailwind-Paletten-Klassen (bg-gray-100, text-blue-600, border-red-300)
        // statt der Tier-2-Tokens (surface-*/ink-*/primary-*/accent-*/status-*).
        // Prüft auf Literale in className-Attributen/-Ausdrücken, deren Wert
        // eine der bekannten Tailwind-Farbfamilien mit -Nummer enthält.
        {
          selector:
            "JSXAttribute[name.name='className'] Literal[value=/\\b(bg|text|border)-(gray|slate|zinc|blue|red|green|yellow|orange|purple|pink|indigo|emerald|amber|rose|teal|cyan|violet|fuchsia|lime|sky)-[0-9]+\\b/]",
          message:
            'Rohe Tailwind-Paletten-Klasse statt Tier-2-Token (surface-*, ink-*, primary-*, accent-*, status-*) — className mit Farbklasse aus dem Palette-Namespace prüfen. Siehe docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md.',
        },
        {
          selector:
            "JSXAttribute[name.name='className'] TemplateElement[value.raw=/\\b(bg|text|border)-(gray|slate|zinc|blue|red|green|yellow|orange|purple|pink|indigo|emerald|amber|rose|teal|cyan|violet|fuchsia|lime|sky)-[0-9]+\\b/]",
          message:
            'Rohe Tailwind-Paletten-Klasse statt Tier-2-Token (surface-*, ink-*, primary-*, accent-*, status-*) — className-Template-String mit Farbklasse aus dem Palette-Namespace prüfen. Siehe docs/SSOT-FRONTEND-REDESIGN-2026-08-14.md.',
        },
      ],
    },
  },
  {
    // Playwright e2e-Tests: kein React-Kontext, Hooks-Regel nicht anwendbar
    files: ['e2e/**/*.{js,ts}'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
    },
  },
  {
    files: ['**/__tests__/**', '**/*.test.{js,jsx}'],
    languageOptions: {
      // globals.vitest statt globals.jest: Projekt nutzt vitest (globals: true in vitest.config.js)
      globals: { ...globals.node, ...globals.vitest },
    },
    rules: { 'no-console': 'off' },
  },
]
