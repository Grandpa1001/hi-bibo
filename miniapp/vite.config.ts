import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// Front serwuje wtyczka bibo-tryby spod korzenia adresu tunelu — ścieżki względne,
// żeby działało też spod dowolnego prefiksu.
export default defineConfig({
  base: "./",
  plugins: [preact()],
  build: { outDir: "dist", emptyOutDir: true, assetsInlineLimit: 0, sourcemap: false },
  server: { host: true, port: 5173 },
});
