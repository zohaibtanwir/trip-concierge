import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirror tsconfig.json "paths": { "@/*": ["./*"] } so imports like
    // `@/auth` and `@/lib/env` resolve identically in tests and runtime.
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
