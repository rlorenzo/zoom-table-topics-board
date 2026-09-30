import { defineConfig } from "vite-plus";

export default defineConfig({
  // Same scope and style as the previous Biome setup: JS/CSS only, 100 cols, double quotes.
  fmt: {
    printWidth: 100,
    ignorePatterns: ["**/*.{html,md,json,jsonc,yml,yaml,toml,py}"],
  },
  lint: {
    // Biome "recommended" ~ Oxlint default (correctness) rules.
    ignorePatterns: ["coverage/**", "docs/**"],
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
    rules: { "vite-plus/prefer-vite-plus-imports": "error" },
  },
  test: {
    // lib.js uses localStorage, so the pure-logic tests run under jsdom.
    environment: "jsdom",
    include: ["**/*.test.js"],
    coverage: {
      provider: "v8",
      // Only the testable pure module is gated. app.js is DOM/event wiring,
      // exercised by the app itself, not by unit tests.
      include: ["lib.js", "engine.js"],
      reporter: ["text", "text-summary"],
      // Floor, not a target (lib.js is fully covered today). Guards regressions.
      thresholds: { statements: 90, branches: 85, functions: 90, lines: 90 },
    },
  },
});
