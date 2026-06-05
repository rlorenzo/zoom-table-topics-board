# Table Topics Board

A live webpage for running **Table Topics** in a meeting. It reads the Zoom
Participants panel automatically (macOS and Windows), rolls a random
participant who hasn't gone yet, and lets you assign them a prompt — then
shows that prompt full-screen for the room. Screen-share the page so everyone
sees who's up and what they've been asked.

One process, one command. No Node, no Zoom account, no credentials.

## Run it

```bash
uv sync
uv run board.py
```

Open <http://localhost:3000> and screen-share that browser tab.

- On macOS with Accessibility granted, or on Windows with the UIA backend
  installed, it auto-reads Zoom's Participants panel every few seconds and
  fills the roster for you.
- Anywhere else (or without permission) it runs in manual-only mode: type
  names in yourself. The webpage is identical either way.

## How it works

1. **Build your topics.** Add a prompt (a headline plus optional details), one
   at a time or pasted in as a block. Topics also live in your browser, so a
   reload or your next meeting pre-fills them — nothing is saved on a server
   and nothing is shared automatically.
2. **Pick someone.** Hit *Pick next participant*. The board rolls a random
   person who hasn't answered yet (the host is skipped by default — you're
   running it). Don't like the draw? Pick again.
3. **Hand them a topic.** Click an open topic. It locks to that person and the
   screen goes full-screen: their name, the prompt, and any details.
4. **Done.** When they finish, hit *Done*. The topic grays out with their name,
   and you're back on the board to pick the next person.

State lives for the meeting only. *Reset* clears assignments and starts a fresh
round with the same topics.

## Auto-reading Zoom (macOS)

Auto-read needs pyobjc and macOS Accessibility permission. Install via
[uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Grant Accessibility permission to the app you run this FROM (Terminal or
iTerm), in System Settings > Privacy & Security > Accessibility, then reopen
that terminal. Start a meeting, open the Participants panel, then run
`uv run board.py`.

Zoom's accessibility tree is undocumented and changes between versions, so if
names do not appear, tune the matcher:

```bash
uv run board.py --anchor-regex 'participants|attendees' --debug
```

Known limitations: virtualized participant lists may only expose names that
are currently scrolled into view, and dial-in users sometimes appear as phone
numbers rather than names.

## Auto-reading Zoom (Windows)

Auto-read on Windows uses UI Automation via the `uiautomation` package, which
`uv sync` installs automatically. No extra permission prompt is required.

## CLI flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `--port` | `3000` | Port for the local web UI |
| `--interval` | `5.0` | Seconds between Zoom panel reads |
| `--no-ax` | off | Manual entry only; never read Zoom |
| `--anchor-regex` | `participant` | Regex that locates the participants subtree |
| `--exclude` | — | Extra comma-separated terms to drop from names |
| `--min-len` | `2` | Minimum length for a string to count as a name |
| `--debug` | off | Print reader diagnostics to stderr |

## Development

```bash
uv sync --dev
uv run pytest          # tests
uv run ruff check .    # lint
uv run mypy            # type-check (strict)
uv run pre-commit run --all-files
```

## Credit

The Zoom-reading engine (accessibility scraping, name cleaning, host
detection, and the HTTP + Server-Sent-Events server pattern) is shared in
spirit with its sibling project, the Zoom Icebreaker tracker.
