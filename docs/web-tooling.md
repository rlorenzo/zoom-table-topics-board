# Web tooling (HTML / CSS / JS)

The Python side of this project (`board.py`, `tests/`) is linted by ruff, mypy,
bandit, lizard, pylint and friends. This document covers the parallel toolchain
for the front-end (`index.html` and, once extracted, `app.js` / `styles.css`).

## Tools

| Tool | Covers | Notes |
| --- | --- | --- |
| [Biome](https://biomejs.dev) `2.4.16` | JS + CSS lint **and** format | Rust-native, single binary. One tool for both languages. |
| [fallow](https://docs.fallow.tools) `2.88.3` | JS dead code, duplication, complexity | Rust-native. Mirrors what `lizard` + `pylint --enable=duplicate-code` do for Python. |
| [html-validate](https://html-validate.org) `11.5.2` | HTML structure + accessibility | The one Node-only tool; Biome/fallow don't validate HTML semantics. |

**oxlint was intentionally skipped.** It's an excellent, very fast linter, but
it's JS/TS-only (no CSS, no HTML) and lint-only (no formatter yet), so Biome
already covers everything it would here. Revisit if the JS grows large enough
that a dedicated ultra-fast lint pass earns its keep.

No `package.json` or `node_modules` is committed. The binaries are fetched on
demand — via pre-commit-managed node environments locally and pinned `npx`
invocations in CI.

## Status: armed but dormant

All of the front-end JS and CSS currently lives **inline** inside `index.html`
(one `<style>` block and one `<script>` block). Biome and fallow operate on
standalone files and cannot see code embedded in HTML, so today:

- **html-validate** runs against `index.html` and is the only active check
  (0 errors, a few warnings — see below).
- **Biome** and **fallow** are configured and wired, but match no files yet, so
  they pass trivially.

The tooling activates automatically once the inline code is extracted (planned
for a follow-up branch off `main`, kept separate so it doesn't collide with the
in-flight UI redesign of `index.html`).

### Extraction convention

For the configs here to "just work" when extraction happens, the inline blocks
should become **repo-root** files referenced from `index.html`:

```html
<link rel="stylesheet" href="styles.css" />
<script src="app.js"></script>
```

- `biome.json` already globs `**/*.js` and `**/*.css`.
- `.fallowrc.jsonc` already declares `app.js` as the entry point.

### Getting full value from fallow

As a single flat browser script, `app.js` has no `import`/`export` graph, so
fallow's headline dead-code features (unused files/exports, circular deps) will
find nothing — you'll get its duplication and complexity passes only. If the JS
is later split into a few **native ES modules** (`<script type="module">`, no
bundler, loads fine over `http://localhost:3000`), fallow's full analysis lights
up. Update the `entry` list in `.fallowrc.jsonc` accordingly.

## Running locally

```bash
# JS + CSS: report problems (no changes)
npx @biomejs/biome@2.4.16 check .
# JS + CSS: fix + format in place
npx @biomejs/biome@2.4.16 check --write .

# HTML structure / accessibility
npx html-validate@11.5.2 index.html

# JS dead code + duplication + complexity (whole tree)
npx fallow@2.88.3
# or, gate just the diff against a base ref:
npx fallow@2.88.3 audit --base main
```

These also run through `pre-commit` (see `.pre-commit-config.yaml`): biome and
html-validate at commit time, fallow at push time (like `pip-audit`).

## html-validate rule choices

`.htmlvalidate.json` extends `html-validate:recommended` with a few pragmatic
adjustments so it passes on the current markup while still catching real
breakage:

- `void-style: off` — self-closing void elements (`<meta />`, `<input />`) are
  valid HTML5; not a battle worth fighting.
- `no-inline-style`, `no-implicit-input-type`, `aria-label-misuse` set to
  `warn` — surfaced but non-blocking while the UI is mid-redesign.

Tighten these to `error` once the redesigned / extracted markup settles.
