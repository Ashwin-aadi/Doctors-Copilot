import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Pinned, not "whatever is free". Vite silently walks to the next port when
  // 5173 is taken -- by another project's container here -- and the result is
  // a stale tab on the old port that looks like the app failed to rebuild.
  // Failing loudly on a busy port is the cheaper mistake.
  server: {
    port: 5174,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        // The framework and the data layer change far less often than our own
        // screens do, so they get their own chunk and stay in the browser
        // cache across deploys instead of being invalidated by every edit.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query", "zustand"],
          i18n: ["i18next", "react-i18next"],
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
