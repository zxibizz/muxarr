import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// `npm run dev` talks to a daemon started with `python -m src.cli serve`;
// docker-compose.dev.yaml points VITE_API_PROXY_TARGET at the backend service.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8710';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
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
