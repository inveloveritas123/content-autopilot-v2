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
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // allowEmptyCatch: leere catch-Blöcke sind in UI-fire-and-forget-Aktionen
      // absichtlich — Fehler werden still ignoriert ohne die UI zu unterbrechen.
      // Das Pattern ist im gesamten Codebase konsistent eingesetzt.
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
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
