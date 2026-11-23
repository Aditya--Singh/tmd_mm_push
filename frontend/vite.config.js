import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The settings of the application are read from frontend/.env, so that the
  // setup script can point the proxy at the backend. A value given in the
  // shell wins over the file.
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    // Set VITE_BASE_PATH to serve the application from a sub-path, for
    // example /news/ when it is hosted behind a reverse proxy next to
    // the landing page.
    base: process.env.VITE_BASE_PATH || env.VITE_BASE_PATH || '/',
    server: {
      host: true,
      allowedHosts: ["newsintel.pnbbank.in", "topmgmtdash.pnbbank.in"],
      // The API is proxied so that the browser stays on a single origin
      // during development, the same way it is behind a reverse proxy in
      // production.
      proxy: {
        '/api': {
          target:
            process.env.VITE_API_PROXY_TARGET ||
            env.VITE_API_PROXY_TARGET ||
            'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
