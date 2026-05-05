import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  server: { port: 5173 },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        job: resolve(__dirname, "job.html"),
      },
    },
  },
});
