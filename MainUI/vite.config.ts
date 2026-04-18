import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

/** Proxy API traffic to FastAPI so the browser uses same-origin URLs (fixes "Failed to fetch" when the UI is opened by IP/hostname, not localhost). Set when starting Vite, e.g. BACKEND_PROXY_TARGET=http://127.0.0.1:8000 */
const backendProxyTarget =
  process.env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8000";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/api": { target: backendProxyTarget, changeOrigin: true },
      "/chat": { target: backendProxyTarget, changeOrigin: true },
      "/rag": { target: backendProxyTarget, changeOrigin: true },
      "/data": { target: backendProxyTarget, changeOrigin: true },
      "/insurance": { target: backendProxyTarget, changeOrigin: true },
      "/dev": { target: backendProxyTarget, changeOrigin: true },
    },
  },
  plugins: [react()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
}));
