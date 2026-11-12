import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The landing page is served on its own port so that it stays a separate
// application from the news frontend it embeds. During development the
// API is proxied through this server, which keeps the browser on a single
// origin and removes the need for CORS in development.
// The backend the API is forwarded to. It is also handed to the application, so that a
// sign-in that cannot go through can say where it was meant to go.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  define: {
    __API_PROXY_TARGET__: JSON.stringify(apiProxyTarget),
  },
  server: {
    host: true,
    port: 5174,
    allowedHosts: ['newsintel.pnbbank.in'],
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
