import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// Frontend-only build. The synthetic dataset snapshot is served as a static asset
// from `public/data/snapshot.json` so the app runs with no backend at all.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: false,
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 900,
  },
});