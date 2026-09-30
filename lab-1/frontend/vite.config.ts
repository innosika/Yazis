/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig(({ mode }) => {
  // `.env` files are not loaded at config-evaluation time, so read them explicitly.
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_TARGET ?? "http://localhost:8010";

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      host: true,
      port: 5173,
      proxy: {
        // In dev the SPA talks to the API container directly (host port 8010 on this
        // machine). http-proxy streams SSE responses without extra configuration.
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
      rollupOptions: {
        output: {
          // Three.js, the charting library and KaTeX are large and only needed on a
          // few routes; splitting them keeps the initial search page fast. Routes are
          // also lazy-loaded, which is what actually keeps these chunks off the page.
          manualChunks: {
            three: ["three", "@react-three/fiber", "@react-three/drei"],
            charts: ["recharts"],
            math: ["katex"],
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      css: false,
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
