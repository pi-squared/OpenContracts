import { defineConfig } from "vitest/config";
export default defineConfig({
  server: { host: "127.0.0.1" },
  test: {
    environment: "jsdom",
    include: ["hp-tests/*.test.tsx"],
    maxWorkers: 1,
  },
});
