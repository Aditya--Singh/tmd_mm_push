import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The development server forwards the API to the analyzer's own backend, so that the
// browser never has to be told where it is. The address is written by the setup script.
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), "");

    return {
        plugins: [react(), tailwindcss()],
        server: {
            port: Number(env.VITE_ANALYZER_DEV_PORT || 5175),
            host: true,
            proxy: {
                "/api": {
                    target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8095",
                    changeOrigin: true,
                },
            },
        },
        build: {
            outDir: "dist",
            emptyOutDir: true,
        },
    };
});
