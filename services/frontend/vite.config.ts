import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// `npm run dev` talks to a daemon started with `python -m src.cli serve`;
// compose.dev.yaml points VITE_API_PROXY_TARGET at the API in the same container.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8710';

export default defineConfig({
  plugins: [react()],
  // Relative asset URLs, resolved against the <base href> the container sets.
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rolldownOptions: {
      output: {
        // Dependencies change far less often than the app, so they cache separately.
        advancedChunks: {
          groups: [
            { name: 'mantine', test: /node_modules[\\/]@mantine/ },
            { name: 'vendor', test: /node_modules/ },
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
  server: {
    // Containers on macOS/Windows bind mounts do not receive inotify events.
    watch: process.env.VITE_WATCH_POLLING === 'true' ? { usePolling: true } : undefined,
    proxy: {
      '/v1': apiTarget,
      '/healthz': apiTarget,
    },
  },
});
