import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = {
  target: "http://127.0.0.1:8000",
  configure(proxy: { on: (event: string, callback: (request: { setHeader: (name: string, value: string) => void }) => void) => void }) {
    const apiKey = process.env.FINRISK_API_KEY;
    if (apiKey) {
      proxy.on("proxyReq", (request) => request.setHeader("X-API-Key", apiKey));
    }
  },
};

export default defineConfig({
  base: process.env.GITHUB_PAGES === "true" ? "/FinRisk-Agent-Studio/" : "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    watch:
      process.env.CHOKIDAR_USEPOLLING === "true"
        ? {
            usePolling: true,
            interval: 1000,
          }
        : undefined,
    proxy: {
      "/workflows": apiProxy,
      "/supply-chain": apiProxy,
      "/agent-runs": apiProxy,
      "/research": apiProxy,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
