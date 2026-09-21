import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to a daemon started with `muxarr serve`.
    proxy: {
      '/v1': 'http://127.0.0.1:8710',
      '/healthz': 'http://127.0.0.1:8710',
    },
  },
});
