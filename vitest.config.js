import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // lib.js uses localStorage, so the pure-logic tests run under jsdom.
    environment: "jsdom",
    include: ["**/*.test.js"],
    coverage: {
      provider: "v8",
      // Only the testable pure module is gated. app.js is DOM/event wiring,
      // exercised by the app itself, not by unit tests.
      include: ["lib.js"],
      reporter: ["text", "text-summary"],
      // Floor, not a target (lib.js is fully covered today). Guards regressions.
      thresholds: { statements: 90, branches: 85, functions: 90, lines: 90 },
    },
  },
});
