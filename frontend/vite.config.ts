import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        timeout: 10 * 60 * 1000,
        proxyTimeout: 10 * 60 * 1000,
        configure(proxy) {
          proxy.on("error", (_error, _request, socket) => {
            if (!("writeHead" in socket)) {
              socket.destroy();
              return;
            }
            if (socket.headersSent || socket.writableEnded) return;
            socket.writeHead(502, { "Content-Type": "application/json" });
            socket.end(
              JSON.stringify({
                error: {
                  code: "backend_unreachable",
                  message: "The API is not running.",
                },
              }),
            );
          });
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
