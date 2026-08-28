import react from "@vitejs/plugin-react";
// `vitest/config` rather than `vite` so the `test` block below is typed.
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxying /api to the backend keeps the browser on one origin, so CORS
      // never comes into play in development.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // An upload runs Modules 1-3 inline, and normalization asks the local
        // model about every label - a large sheet legitimately takes minutes.
        // The default 30s proxy timeout would abort a request the backend is
        // still working on, which looks like a server fault and is not one.
        timeout: 10 * 60 * 1000,
        proxyTimeout: 10 * 60 * 1000,
        configure(proxy) {
          // With no handler, a refused connection reaches the browser as a
          // bare 500, so "the backend is not running" was reported as
          // "500 Internal Server Error - something went wrong on the server":
          // it blamed a server that was not there to be blamed. Answer with a
          // 502 in this project's own error envelope instead, so the client
          // can say what is actually wrong.
          proxy.on("error", (_error, _request, socket) => {
            // On an upgrade/CONNECT failure the third argument is a raw
            // socket, which has no writeHead.
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
