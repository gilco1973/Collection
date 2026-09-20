/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE ?? "/",
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.KB_API_URL ?? "http://127.0.0.1:8765", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/test/**", "src/i18n/locales/**", "src/vite-env.d.ts", "src/speech.d.ts"],
      thresholds: { lines: 87, functions: 87, branches: 87, statements: 87 },
    },
  },
});
