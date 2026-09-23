import '@testing-library/jest-dom/vitest';
import { notifications } from '@mantine/notifications';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// jsdom implements neither of these, and Mantine calls both on mount.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

window.ResizeObserver = ResizeObserverStub;
window.scrollTo = vi.fn();

afterEach(() => {
  cleanup();
  // The notification store is module-global and would leak into the next test.
  notifications.clean();
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
