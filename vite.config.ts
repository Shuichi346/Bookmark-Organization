import { defineConfig } from "vite";
export default defineConfig({build:{outDir:"src/bookmark_organization/static",emptyOutDir:true,manifest:true,rollupOptions:{input:"frontend/main.ts"}}});
