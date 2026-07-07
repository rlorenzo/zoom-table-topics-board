# Web tooling (HTML / CSS / JS)

The Python side (`board.py`, `tests/`) is linted by ruff, mypy, bandit, lizard,
pylint and covered by pytest. This document covers the parallel toolchain for
the front-end.

## Front-end layout

The page used to be a single `index.html` with everything inline. It's now split
so the JS is lintable and testable:

| File | What it is |
| --- | --- |
| `index.html` | Markup only; links `styles.css` and loads `app.js` as a module. |
| `styles.css` | All styles (was the inline `<style>`). |
| `app.js` | The browser app: DOM rendering, event wiring, SSE. Imports from `lib.js` and `engine.js`. |
| `lib.js` | Pure, DOM-free helpers (`escapeHtml`, `parsePaste`, `eligibleNames`, the topic-localStorage functions, `fmtTime`). No side effects on import — unit-tested. |
| `engine.js` | Browser-side, DOM-free port of `board.py`'s `State`: drives the standalone (no-server) board. Unit-tested. |
| `lib.test.js` | Vitest unit tests for `lib.js`. |
| `engine.test.js` | Vitest unit tests for `engine.js`, mirroring `tests/test_state.py`. |

`board.py` serves `app.js`, `lib.js`, `engine.js`, and `styles.css` as static
files via an explicit allowlist (`STATIC_FILES`) — the path is never derived
from the request, so there's no traversal surface.

## Tools

| Tool | Covers |
| --- | --- |
| [Biome](https://biomejs.dev) | JS + CSS lint **and** format (one binary). |
| [Vitest](https://vitest.dev) + jsdom | Unit tests for `lib.js` and `engine.js`, with v8 coverage. |
| [fallow](https://docs.fallow.tools) | JS dead-code + duplication (and complexity, on demand). |
| [html-validate](https://html-validate.org) | HTML structure + accessibility. |

**oxlint** was intentionally skipped — JS/TS-only and lint-only, so Biome already
covers its ground here.

## package.json, not npx

All versions live in `package.json` and are locked in `package-lock.json`, so
installs are reproducible (`npm ci`) and auditable (`npm audit`). Run `npm
install` once — the Node-side counterpart to `uv sync` for Python. `node_modules`
is not committed.

```bash
npm install          # one-time (and after package.json changes)

npm run lint         # biome check .          (lint + format check)
npm run format       # biome check --write .  (fix + format)
npm run validate:html
npm test             # vitest run
npm run test:cov     # vitest run --coverage  (gated, see below)
npm run deadcode     # fallow --skip health   (dead code + duplication)
npm run health       # fallow health          (complexity/CRAP report, on demand)
npm run check        # lint + html + test:cov + deadcode
```

## How it runs in CI and pre-commit

- **CI** has a dedicated `web` job: `npm ci`, then each check via its `npm run`
  script. The Python `lint` job skips the web hooks (`SKIP=...`) because it has
  no `node_modules`.
- **pre-commit** runs biome + html-validate at commit time and vitest + fallow
  at push time, using the local `node_modules` (so `npm install` is required,
  alongside `uv sync`).

## Coverage gate

`vitest.config.js` gates `lib.js` and `engine.js` at a floor
(statements/functions/lines 90, branches 85). It's a regression guard, not a
target — both are fully covered today. `app.js` is deliberately out of scope
for unit tests: it's DOM/event wiring, exercised by running the app, not in
isolation.

## Notable config choices

- **fallow ignores CSS** (`ignorePatterns: ["**/*.css"]`): fallow is a JS/TS
  analyzer and can't see that `index.html` links `styles.css`, so it would
  otherwise report the stylesheet as an unused file.
- **fallow's `health` (complexity/CRAP) is not gated**: `app.js` is intentionally
  untested DOM code, which inflates CRAP. The gate is scoped to the dead-code +
  duplication checks; `npm run health` gives the complexity report on demand.
- **Biome CSS rules `noImportantStyles` and `noDescendingSpecificity` are off**:
  the `!important` rules are the deliberate reduced-motion accessibility
  overrides, and descending-specificity is noisy on hand-authored CSS.
- **html-validate** relaxes a few opinionated rules (`void-style` off; inline
  style / implicit input type / aria-label misuse as warnings) so it passes on
  the current markup while still catching real structural breakage.
