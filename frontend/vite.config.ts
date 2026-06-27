import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
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
      "/workflows": "http://127.0.0.1:8000",
      "/supply-chain": "http://127.0.0.1:8000",
      "/agent-runs": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
