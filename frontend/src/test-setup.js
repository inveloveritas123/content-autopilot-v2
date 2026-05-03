import '@testing-library/jest-dom/vitest'

// localStorage stub für Tests die useEffect/useState mit localStorage nutzen
if (typeof window !== 'undefined' && !window.localStorage._stubbed) {
  const store = new Map()
  window.localStorage = {
    getItem: (k) => store.has(k) ? store.get(k) : null,
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
    _stubbed: true,
  }
}
