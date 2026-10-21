import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The landing page is served on its own port so that it stays a separate
// application from the news frontend it embeds. During development the
// API is proxied through this server, which keeps the browser on a single
// origin and removes the need for CORS in development.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5174,
    allowedHosts: ['newsintel.pnbbank.in'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
