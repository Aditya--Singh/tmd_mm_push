import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The Data Analyzer of the Executive Intelligence Hub.
//
// The built interface is served from this app's own origin by the backend, so there is
// one address to allow in the frame headers and one address to put in the hub's
// settings. During development the API is proxied through this server, which keeps the
// browser on a single origin.
export default defineConfig(({ mode }) => {
  // The settings are read from dataanalyzer/.env, so that the setup script can point the
  // proxy at the port this app really runs on. A value given in the shell wins.
  const env = loadEnv(mode, process.cwd(), "");

  const port = Number(env.ANALYZER_PORT || env.PORT || 8095);

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5176,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${port}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
