import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  base: "/food-map/static/",
  plugins: [vue()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
