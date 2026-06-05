# Contributing to Table Topics

Thank you for considering contributing to Table Topics!

## Development Setup

This project has two toolchains: [uv](https://docs.astral.sh/uv/) for the Python
side (the Zoom-reading engine and local server) and npm for the front-end
assets (HTML/CSS/JS).

1. **Clone the repository**:

    ```bash
    git clone https://github.com/rlorenzo/zoom-table-topics-board.git
    cd zoom-table-topics-board
    ```

2. **Install dependencies and set up pre-commit**:

    ```bash
    uv sync --dev
    npm install
    uv run pre-commit install
    ```

## Workflow

1. **Create a branch** for your change.
2. **Make your changes**.
3. **Run checks locally** before committing:

    ```bash
    uv run pre-commit run --all-files
    ```

    On the Python side this runs `ruff` (linting/formatting), `bandit` and
    `gitleaks` (security), `lizard` (complexity), `mypy` (strict types),
    `pylint` (duplicate code), `pytest`, and `pymarkdown`. On the web side it
    runs `biome` (JS/CSS lint and format), `html-validate` (HTML structure and
    accessibility), `vitest` (front-end tests), and `fallow` (dead code). See
    [`docs/web-tooling.md`](docs/web-tooling.md) for the web setup.
4. **Submit a Pull Request**.

## Guidelines

- **Code Quality**: Ensure your code follows the existing style (Python checked
  by `ruff`, front-end by `biome`).
- **Documentation**: Update `README.md` or `DESIGN.md` if your change adds or alters functionality.
- **Accessibility**: This project prioritizes accessibility (keyboard navigation, ARIA, reduced motion). Ensure your changes do not degrade the experience for users with assistive technologies.
- **Small PRs**: Favor small, focused PRs over large ones.

## Reporting Issues

Use the GitHub Issue tracker to report bugs or suggest features. Please provide as much detail as possible, including steps to reproduce the issue.
