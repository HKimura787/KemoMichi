import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build goes into the Python package so `kemo serve` can serve it.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/kemoserver/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
