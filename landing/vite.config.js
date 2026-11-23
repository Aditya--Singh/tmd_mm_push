import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The landing page is served on its own port so that it stays a separate
// application from the news frontend it embeds. During development the
// API is proxied through this server, which keeps the browser on a single
// origin and removes the need for CORS in development.
export default defineConfig(({ mode }) => {
  // The settings of the landing page are read from landing/.env, so that the
  // setup script can point the proxy at the backend. A value given in the
  // shell wins over the file.
  const env = loadEnv(mode, process.cwd(), '')

  // The backend the API is forwarded to. It is also handed to the application,
  // so that a sign-in that cannot go through can say where it was meant to go.
  const apiProxyTarget =
    process.env.VITE_API_PROXY_TARGET ||
    env.VITE_API_PROXY_TARGET ||
    'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    define: {
      __API_PROXY_TARGET__: JSON.stringify(apiProxyTarget),
    },
    server: {
      host: true,
      port: 5174,
      allowedHosts: ['newsintel.pnbbank.in', 'topmgmtdash.pnbbank.in'],
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
