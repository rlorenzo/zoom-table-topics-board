#!/usr/bin/env python3
"""
board.py  --  Zoom Table Topics board, single local process.

One command. Reads participant names from Zoom's Participants panel via the
macOS Accessibility API (or Windows UI Automation) and serves a web UI that
lets you roll a random participant who hasn't gone yet and assign them a
Table Topic. No Node, no browser automation, no Zoom credentials.

    python3 board.py                 # serve UI + auto-read Zoom (if supported)
    python3 board.py --no-ax         # manual entry only (no Zoom reading)
    python3 board.py --interval 5    # re-read the panel every 5s
    python3 board.py --port 3000
    python3 board.py --anchor-regex 'participants|attendees'
    python3 board.py --exclude "pin,spotlight" --debug

Then open http://localhost:3000 and screen-share that browser tab.

If pyobjc is missing or Accessibility permission is not granted, it prints a
notice and runs in manual-only mode. The web UI is fully usable either way.

The Zoom-reading engine (accessibility scraping, name cleaning, host
detection, the poller, the HTTP+SSE server pattern) is shared in spirit with
the sibling project `zoom-icebreaker`; what differs here is the domain: Table
Topics and random assignment instead of a one-tap "introduced" toggle.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import queue
import random
import re
import sys
import threading
import time
from collections.abc import Callable, Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar, TypedDict
from urllib.parse import urlparse

# --- Optional accessibility support (degrades gracefully) ------------------
# macOS: pyobjc + ApplicationServices (AX*)
# Windows: uiautomation (UI Automation / UIA)
# Either backend is optional; if neither is available the app runs in
# manual-only mode (still fully usable).
AX_AVAILABLE = False
try:
    from AppKit import NSWorkspace
    from ApplicationServices import (
        AXIsProcessTrusted,
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
    )

    AX_AVAILABLE = True
except ImportError:
    pass

UIA_AVAILABLE = False
try:
    import uiautomation as _uia

    UIA_AVAILABLE = True
except ImportError:
    pass


class Person(TypedDict):
    name: str
    is_host: bool


class Participant(TypedDict):
    id: str
    name: str
    source: str  # "auto" (Zoom panel) | "manual" | "demo"
    joinTime: float
    leftTime: float | None
    present: bool
    answered: bool
    is_host: bool
    excluded: bool  # opted out of the random roll ("don't call them")


class Topic(TypedDict):
    id: str
    headline: str
    details: str
    status: str  # "open" | "active" | "done"
    assignee: str | None  # participant id, or None


DEFAULT_BUNDLE = "us.zoom.xos"
DEFAULT_WIN_PROCESS = "Zoom.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(HERE, "index.html")
APP_JS = os.path.join(HERE, "app.js")
LIB_JS = os.path.join(HERE, "lib.js")
ENGINE_JS = os.path.join(HERE, "engine.js")
STYLES_CSS = os.path.join(HERE, "styles.css")

# Static web assets served next to index.html (extracted from the old
# single-file page). An explicit allowlist — the filesystem path is never
# derived from the request, so there is no path-traversal surface.
STATIC_FILES: dict[str, tuple[str, str]] = {
    "/app.js": (APP_JS, "text/javascript; charset=utf-8"),
    "/lib.js": (LIB_JS, "text/javascript; charset=utf-8"),
    "/engine.js": (ENGINE_JS, "text/javascript; charset=utf-8"),
    "/styles.css": (STYLES_CSS, "text/css; charset=utf-8"),
}

# --- Name cleaning / filtering --------------------------------------------
# Any comma-separated list of role words in trailing parens: "(host)",
# "(host, me)", "(Co-host, me)", ... — Zoom mixes hyphenation freely.
_ROLE = r"(?:co-?host|host|me|guest|you)"
ANNOT = re.compile(
    rf"\s*\({_ROLE}(?:\s*,\s*{_ROLE})*\)\s*$",
    re.IGNORECASE,
)
ROLEWORD = re.compile(r"\b(host|co-?host|guest|me|you)\b\s*$", re.IGNORECASE)
# Trailing "(N)" counts appear on chat panel section headers
# ("Joined (1)", "Not joined (0)") — not on real names.
COUNT_TAIL = re.compile(r"\s*\(\d+\)\s*$")
# Detects the primary host (not cohost): "(host)" or "(host, me)".
HOST_DETECT = re.compile(r"\(host(?:\s*,\s*me)?\)", re.IGNORECASE)

DEFAULT_EXCLUDE = [
    "mute",
    "unmute",
    "more",
    "invite",
    "raise hand",
    "lower hand",
    "participants",
    "search",
    "chat",
    "share",
    "record",
    "reactions",
    "ask to unmute",
    "rename",
    "remove",
    "host",
    "co-host",
    "cohost",
    "guest",
    "waiting room",
    "admit",
    "everyone",
    "stop video",
    "start video",
    "security",
    "apps",
    "speaker view",
    "gallery view",
    "leave",
    "end meeting",
    "raise",
    "allow",
    "deny",
    "close",
    "pop out",
    "mute all",
    "unmute all",
    # Zoom chat panel chrome that can leak in if the chat panel is
    # adjacent to or shares a subtree with the participants panel.
    "joined",
    "not joined",
    "who can see your messages",
    "see your messages",
    "in this meeting",
    "send to",
    # "participants" alone wouldn't catch "participant(s) sent" — Zoom's
    # delivery indicator. The singular form does, because `(` is a word
    # boundary in regex.
    "participant",
    "panelist",
    "panelists",
]


def _term_pattern(term: str) -> str:
    """Escape one exclude term, anchoring with \\b only where the term's edge
    is a word character — \\b before "(" or after ")" can never match, which
    would silently disable a user-supplied term like "(external)"."""
    pat = re.escape(term)
    if re.match(r"\w", term):
        pat = r"\b" + pat
    if re.search(r"\w\Z", term):
        pat += r"\b"
    return pat


def build_exclude_re(terms: Iterable[str]) -> re.Pattern[str]:
    ordered = sorted(set(terms), key=len, reverse=True)
    return re.compile(
        "(?:" + "|".join(_term_pattern(t) for t in ordered) + ")",
        re.IGNORECASE,
    )


def clean_name(raw: str) -> str:
    s = raw.strip()
    s = COUNT_TAIL.sub("", s)
    s = ANNOT.sub("", s)
    s = ROLEWORD.sub("", s).strip(" ,-")
    return s.strip()


def looks_like_name(s: str, exclude_re: re.Pattern[str], min_len: int) -> bool:
    if len(s) < min_len:
        return False
    if exclude_re.search(s):
        return False
    if re.fullmatch(r"[\d\W_]+", s):
        return False
    return len(s) <= 60


# --- Accessibility reading -------------------------------------------------
TEXT_ROLES = {"AXStaticText", "AXCell", "AXButton", "AXRow", "AXTextField"}

# Zoom's chat panel has a recipient picker that mentions "participants",
# so it can match the participant anchor regex. We reject anchors that
# look like chat so the harvester doesn't slurp up chat-panel labels
# (e.g. "Joined (N)", "Who can see your messages") as participant names.
CHAT_HINT_RE = re.compile(r"\bchat\b", re.IGNORECASE)


def _attr(el: Any, name: str) -> Any:
    err, val = AXUIElementCopyAttributeValue(el, name, None)
    return None if err != 0 else val


def _find_pid(bundle_id: str) -> int | None:
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == bundle_id:
            return int(app.processIdentifier())
    return None


def _node_text(el: Any) -> str:
    for a in ("AXValue", "AXTitle", "AXDescription"):
        v = _attr(el, a)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


# The text-ish AX attributes anchor matching reads. Chat rejection searches the
# same joined haystack, so the two can never drift apart.
AX_HAY_ATTRS = (
    "AXTitle",
    "AXDescription",
    "AXRoleDescription",
    "AXHelp",
    "AXIdentifier",
)


def _walk(
    el: Any,
    children_of: Callable[[Any], Iterable[Any]],
    visit: Callable[[Any], bool],
    max_nodes: int,
    depth: int = 0,
    counter: list[int] | None = None,
) -> None:
    """Depth- and size-guarded DFS shared by the anchor and text collectors on
    both accessibility backends. `visit` returns True to prune descent below
    `el` (an anchor was found, or the node went invalid mid-traversal)."""
    counter = counter or [0]
    if counter[0] >= max_nodes or depth > 40:
        return
    counter[0] += 1
    if visit(el):
        return
    for c in children_of(el):
        _walk(c, children_of, visit, max_nodes, depth + 1, counter)


def _ax_children(el: Any) -> Iterable[Any]:
    return _attr(el, "AXChildren") or []


def _collect_anchors(el: Any, pat: re.Pattern[str], found: list[Any]) -> None:
    def visit(node: Any) -> bool:
        hay = " ".join(str(_attr(node, a) or "") for a in AX_HAY_ATTRS)
        if pat.search(hay) and not CHAT_HINT_RE.search(hay):
            found.append(node)
            return True
        return False

    _walk(el, _ax_children, visit, 8000)


def _collect_texts(el: Any, out: list[str]) -> None:
    def visit(node: Any) -> bool:
        if _attr(node, "AXRole") in TEXT_ROLES:
            t = _node_text(node)
            if t:
                out.append(t)
        return False

    _walk(el, _ax_children, visit, 6000)


def _filter_and_dedupe(
    raw: Iterable[str], exclude_re: re.Pattern[str], min_len: int
) -> list[Person]:
    """Common post-processing: clean names, detect host, dedupe.

    Host detection runs on the raw text BEFORE cleaning, since the
    "(host)" / "(host, me)" annotations are stripped by clean_name.
    """
    people: list[Person] = []
    by_name: dict[str, Person] = {}
    for t in raw:
        is_host = bool(HOST_DETECT.search(t))
        n = clean_name(t)
        if not looks_like_name(n, exclude_re, min_len):
            continue
        key = n.lower()
        existing = by_name.get(key)
        if existing is not None:
            # A later token like "Alice (host)" may carry the host flag the
            # bare "Alice" seen first did not — keep it rather than drop it.
            existing["is_host"] = existing["is_host"] or is_host
            continue
        person: Person = {"name": n, "is_host": is_host}
        by_name[key] = person
        people.append(person)
    return people


def _read_zoom_participants_ax(
    args: argparse.Namespace, exclude_re: re.Pattern[str]
) -> list[Person] | None:
    """macOS reader. Returns list[Person] or None if Zoom isn't running."""
    pid = _find_pid(args.bundle)
    if pid is None:
        return None
    app_el = AXUIElementCreateApplication(pid)
    pat = re.compile(args.anchor_regex, re.IGNORECASE)
    anchors: list[Any] = []
    _collect_anchors(app_el, pat, anchors)
    roots = anchors if anchors else [app_el]
    raw: list[str] = []
    for r in roots:
        _collect_texts(r, raw)
    if args.debug:
        sys.stderr.write(f"[ax] {len(anchors)} anchor(s), {len(raw)} raw nodes\n")
    return _filter_and_dedupe(raw, exclude_re, args.min_len)


# --- Windows UI Automation reading -----------------------------------------
# UIA control types whose Name is typically a participant or text label.
UIA_TEXT_TYPES = {
    "TextControl",
    "ListItemControl",
    "DataItemControl",
    "ButtonControl",
    "EditControl",
}


def _uia_zoom_windows() -> list[Any]:
    """Return top-level Zoom windows. Empty if Zoom isn't running."""
    try:
        desktop = _uia.GetRootControl()
    except Exception:
        return []
    found: list[Any] = []
    for w in desktop.GetChildren():
        try:
            cls = (w.ClassName or "").lower()
            name = (w.Name or "").lower()
            if "zoom" in cls or "zoom" in name:
                found.append(w)
        except Exception:  # nosec B112 — UIA/COM can raise on some windows; skip them
            continue
    return found


def _uia_node_text(el: Any) -> str:
    """Best-effort text extraction from a UIA element."""
    for attr in ("Name", "AutomationId"):
        v = getattr(el, attr, None)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _uia_hay(el: Any) -> str | None:
    """Join an element's text-ish UIA properties for anchor matching. Returns
    None if a COM error fires — the element was invalidated mid-traversal
    (Zoom redraws the panel), so the caller should skip it, not crash."""
    try:
        return " ".join(
            str(getattr(el, a, "") or "")
            for a in ("Name", "LocalizedControlType", "AutomationId", "HelpText")
        )
    except Exception:
        return None


def _uia_children(el: Any) -> list[Any]:
    try:
        return list(el.GetChildren())
    except Exception:
        return []


def _uia_collect_anchors(el: Any, pat: re.Pattern[str], found: list[Any]) -> None:
    def visit(node: Any) -> bool:
        hay = _uia_hay(node)
        if hay is None:
            return True  # invalidated mid-traversal: skip this subtree
        if pat.search(hay) and not CHAT_HINT_RE.search(hay):
            found.append(node)
            return True
        return False

    _walk(el, _uia_children, visit, 8000)


def _uia_collect_texts(el: Any, out: list[str]) -> None:
    def visit(node: Any) -> bool:
        try:
            if (getattr(node, "ControlTypeName", "") or "") in UIA_TEXT_TYPES:
                t = _uia_node_text(node)
                if t:
                    out.append(t)
        except Exception:
            # Invalidated UIA/COM node mid-traversal — skip this subtree.
            return True
        return False

    _walk(el, _uia_children, visit, 6000)


def _read_zoom_participants_uia(
    args: argparse.Namespace, exclude_re: re.Pattern[str]
) -> list[Person] | None:
    """Windows reader. Returns list[Person] or None if Zoom isn't running."""
    windows = _uia_zoom_windows()
    if not windows:
        return None
    pat = re.compile(args.anchor_regex, re.IGNORECASE)
    anchors: list[Any] = []
    for w in windows:
        _uia_collect_anchors(w, pat, anchors)
    roots = anchors if anchors else windows
    raw: list[str] = []
    for r in roots:
        _uia_collect_texts(r, raw)
    if args.debug:
        sys.stderr.write(f"[uia] {len(anchors)} anchor(s), {len(raw)} raw nodes\n")
    return _filter_and_dedupe(raw, exclude_re, args.min_len)


# --- Reader dispatch -------------------------------------------------------
def read_zoom_participants(
    args: argparse.Namespace, exclude_re: re.Pattern[str]
) -> list[Person] | None:
    """Dispatch to the right backend based on platform. None == Zoom not running."""
    if sys.platform == "darwin" and AX_AVAILABLE:
        return _read_zoom_participants_ax(args, exclude_re)
    if sys.platform == "win32" and UIA_AVAILABLE:
        return _read_zoom_participants_uia(args, exclude_re)
    return None


# --- Demo mode sample data -------------------------------------------------
# Loaded by start_demo() so a first-time host can try the whole flow (roll a
# name, hand over a prompt, run the focus view) without a live Zoom meeting.
# Stopping the demo wipes all of it back to a clean slate. The host is listed
# first so they land in order[0]; they're a full participant too, so a sample
# round has seven eligible speakers.
DEMO_PARTICIPANTS: list[tuple[str, bool]] = [
    ("Sam Rivera", True),  # runs the board; the HOST badge, but rolled like anyone
    ("Maya Chen", False),
    ("Diego Santos", False),
    ("Priya Patel", False),
    ("Logan Brooks", False),
    ("Aisha Okafor", False),
    ("Noah Kim", False),
]

DEMO_TOPICS: list[dict[str, str]] = [
    {
        "headline": "What's a small win you had this week?",
        "details": "Anything counts. Keep it to a minute or so.",
    },
    {
        "headline": "If you could instantly master one skill, what would it be?",
        "details": "",
    },
    {
        "headline": "Describe a place you'd happily go back to.",
        "details": "Tell us what makes it worth a second visit.",
    },
    {"headline": "What's the best advice you never took?", "details": ""},
    {"headline": "What everyday thing are you quietly great at?", "details": ""},
    {
        "headline": "If this week had a theme song, what would it be?",
        "details": "No wrong answers. Bonus points for humming a bar.",
    },
]


# --- State -----------------------------------------------------------------
class State:
    """In-memory, per-meeting state. Ephemeral: nothing is persisted server-side.

    Holds the participant roster (auto-read from Zoom and/or added by hand),
    the Table Topics, the currently *selected* participant (rolled but not yet
    assigned a topic), and the *active* topic (the one on the focus screen).
    Every mutation broadcasts a fresh snapshot to all SSE clients.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.started_at = time.time() * 1000
        self.participants: dict[str, Participant] = {}  # id -> participant
        self.order: list[str] = []  # participant ids in display order
        self.topics: dict[str, Topic] = {}  # id -> topic
        self.topic_order: list[str] = []  # topic ids in display order
        self.selected_pid: str | None = None  # rolled person awaiting a topic
        self.active_topic_id: str | None = None  # topic currently on the focus view
        self.demo = False  # True while the sample meeting is loaded (try-it mode)
        self.clients: set[queue.Queue[str]] = set()  # one Queue per SSE client
        self._topic_seq = 0  # monotonic, never reused even across reset

    # --- id helpers --------------------------------------------------------
    @staticmethod
    def _id(prefix: str, name: str) -> str:
        h = hashlib.sha1(name.lower().encode(), usedforsecurity=False).hexdigest()[:12]
        return prefix + h

    def _new_topic_id(self) -> str:
        self._topic_seq += 1
        return f"t{self._topic_seq}"

    # --- participant bookkeeping (shared with the icebreaker engine) -------
    def _upsert(self, pid: str, name: str, source: str) -> bool:
        """Insert or refresh a participant. Order is appended to on first sight.
        `source` records where the entry came from ("auto" | "manual" | "demo")
        so e.g. only auto-read people are marked left when the panel loses them.
        """
        p = self.participants.get(pid)
        if p:
            changed = bool(
                not p["present"]
                or p["leftTime"] is not None
                or (name and name != p["name"])
            )
            p["present"] = True
            p["leftTime"] = None
            if name:
                p["name"] = name
            return changed
        self.participants[pid] = {
            "id": pid,
            "name": name or "Guest",
            "source": source,
            "joinTime": time.time() * 1000,
            "leftTime": None,
            "present": True,
            "answered": False,
            "is_host": False,
            "excluded": False,
        }
        if pid not in self.order:
            self.order.append(pid)
        return True

    def _current_host(self) -> str | None:
        return next(
            (pid for pid, p in self.participants.items() if p.get("is_host")),
            None,
        )

    def _settle_host(self, host_pid: str) -> bool:
        """Promote `host_pid` to sole host (most-recent wins) and pin to order[0]."""
        changed = False
        for ppid, p in self.participants.items():
            should_be = ppid == host_pid
            if bool(p.get("is_host")) != should_be:
                p["is_host"] = should_be
                changed = True
        if host_pid in self.order and self.order[0] != host_pid:
            self.order.remove(host_pid)
            self.order.insert(0, host_pid)
            changed = True
        return changed

    def _mark_missing_as_left(self, seen_pids: set[str], now: float) -> bool:
        """Mark auto-read participants no longer in the panel as left. Manual
        and demo entries are never panel-tracked, so they're left alone."""
        changed = False
        for pid, p in self.participants.items():
            if p["source"] == "auto" and pid not in seen_pids and p["present"]:
                p["present"] = False
                p["leftTime"] = now
                # A rolled-but-unassigned speaker who leaves the call shouldn't
                # stay "selected" — clients would keep showing the picking view
                # for someone no longer here.
                if self.selected_pid == pid:
                    self.selected_pid = None
                changed = True
        return changed

    # --- snapshot / broadcast ---------------------------------------------
    def _topic_view(self, t: Topic) -> dict[str, object]:
        assignee: dict[str, str] | None = None
        aid = t["assignee"]
        if aid and aid in self.participants:
            ap = self.participants[aid]
            assignee = {"id": ap["id"], "name": ap["name"]}
        return {
            "id": t["id"],
            "headline": t["headline"],
            "details": t["details"],
            "status": t["status"],
            "assignee": assignee,
        }

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            by_id = {pid: dict(p) for pid, p in self.participants.items()}
            ordered = [by_id[pid] for pid in self.order if pid in by_id]
            # Defensive: include any participant not in order at the end.
            order_set = set(self.order)
            for pid, p in by_id.items():
                if pid not in order_set:
                    ordered.append(p)
            topics = [
                self._topic_view(self.topics[tid])
                for tid in self.topic_order
                if tid in self.topics
            ]
            selected: dict[str, str] | None = None
            sid = self.selected_pid
            if sid and sid in self.participants:
                sp = self.participants[sid]
                selected = {"id": sp["id"], "name": sp["name"]}
            return {
                "startedAt": self.started_at,
                "participants": ordered,
                "topics": topics,
                "selected": selected,
                "activeTopicId": self.active_topic_id,
                "demo": self.demo,
            }

    def broadcast(self) -> None:
        data = "data: " + json.dumps(self.snapshot()) + "\n\n"
        # Copy under the lock: handler threads add/discard clients concurrently,
        # so iterating the live set could raise "set changed size during iteration".
        with self.lock:
            clients = list(self.clients)
        for q in clients:
            with contextlib.suppress(Exception):
                q.put_nowait(data)

    # --- participant mutations --------------------------------------------
    def add_manual(self, name: str) -> None:
        with self.lock:
            self._upsert(self._id("m", name + str(time.time())), name, "manual")
        self.broadcast()

    def _upsert_seen(
        self, people: list[Person], seen: set[str]
    ) -> tuple[str | None, bool]:
        """Upsert each named person, recording their id in `seen`. Returns the
        detected host pid (if any) and whether anything changed. The caller
        (sync_participants) owns the lock."""
        host_pid: str | None = None
        changed = False
        for entry in people:
            nm = str(entry.get("name") or "").strip()
            if not nm:
                continue
            pid = self._id("a", nm)
            seen.add(pid)
            if entry.get("is_host"):
                host_pid = pid
            if self._upsert(pid, nm, "auto"):
                changed = True
        return host_pid, changed

    def sync_participants(self, people: list[Person]) -> bool:
        """`people` is a list of {"name": str, "is_host": bool}."""
        now = time.time() * 1000
        with self.lock:
            # While the sample meeting is loaded, the demo owns the roster.
            # Ignore live Zoom reads so real names can't leak into the demo
            # (and so leaving the demo's "speakers" can't be marked as left).
            if self.demo:
                return False
            seen: set[str] = set()
            host_pid, changed = self._upsert_seen(people, seen)
            if host_pid is not None and self._settle_host(host_pid):
                changed = True
            if self._mark_missing_as_left(seen, now):
                changed = True
        if changed:
            self.broadcast()
        return changed

    def set_host(self, pid: str, val: bool) -> bool:
        with self.lock:
            if pid not in self.participants:
                return False
            if val:
                self._settle_host(pid)
            else:
                self.participants[pid]["is_host"] = False
        self.broadcast()
        return True

    def remove(self, pid: str) -> None:
        with self.lock:
            self.participants.pop(pid, None)
            if pid in self.order:
                self.order.remove(pid)
            if self.selected_pid == pid:
                self.selected_pid = None
            # Free any in-progress topic this person held — an active topic
            # can't keep a removed assignee. Completed (done) topics stay done:
            # tidying the roster shouldn't resurrect a finished prompt and make
            # it eligible again this round.
            for t in self.topics.values():
                if t["assignee"] == pid and t["status"] != "done":
                    t["assignee"] = None
                    t["status"] = "open"
                    if self.active_topic_id == t["id"]:
                        self.active_topic_id = None
        self.broadcast()

    # --- topic mutations ---------------------------------------------------
    def _make_topic(self, headline: str, details: str) -> str:
        tid = self._new_topic_id()
        self.topics[tid] = {
            "id": tid,
            "headline": headline,
            "details": details,
            "status": "open",
            "assignee": None,
        }
        self.topic_order.append(tid)
        return tid

    def add_topic(self, headline: str, details: str = "") -> str | None:
        h = str(headline or "").strip()
        if not h:
            return None
        with self.lock:
            tid = self._make_topic(h, str(details or "").strip())
        self.broadcast()
        return tid

    def add_topics(self, items: list[Any], replace: bool = False) -> int:
        """Bulk add. `items` is a list of {"headline":..., "details":...}.

        With replace=True the whole topic set is cleared first — used by the
        browser's localStorage re-seed and the "clear & reload" path.
        """
        added = 0
        with self.lock:
            if replace:
                self.topics.clear()
                self.topic_order.clear()
                self.active_topic_id = None
                # A pending roll has nothing to be assigned to anymore; drop it
                # so the client doesn't strand on the picking view with 0 topics.
                self.selected_pid = None
            for raw in items:
                it = raw if isinstance(raw, dict) else {}
                h = str(it.get("headline", "")).strip()
                if not h:
                    continue
                self._make_topic(h, str(it.get("details", "")).strip())
                added += 1
        self.broadcast()
        return added

    def edit_topic(self, tid: str, headline: str, details: str) -> bool:
        h = str(headline or "").strip()
        if not h:
            return False
        with self.lock:
            t = self.topics.get(tid)
            if not t:
                return False
            t["headline"] = h
            t["details"] = str(details or "").strip()
        self.broadcast()
        return True

    def remove_topic(self, tid: str) -> bool:
        with self.lock:
            t = self.topics.pop(tid, None)
            if not t:
                return False
            if tid in self.topic_order:
                self.topic_order.remove(tid)
            if self.active_topic_id == tid:
                self.active_topic_id = None
        self.broadcast()
        return True

    # --- selection & assignment -------------------------------------------
    def _holds_active_topic(self, pid: str) -> bool:
        """True while `pid` is the assignee of an in-progress (active) topic:
        they already have the mic, so rolling or selecting them again would
        hand one person two simultaneous topics."""
        return any(
            t["assignee"] == pid and t["status"] == "active"
            for t in self.topics.values()
        )

    def _eligible_pool(self, exclude_pid: str | None) -> list[str]:
        """Participants who can be rolled: present, not yet answered, not opted
        out (excluded), not already speaking on an active topic, and not the
        just-excluded person from a 'pick someone else'. The host is a full
        participant and is rolled like anyone else."""
        pool = []
        for pid in self.order:
            p = self.participants.get(pid)
            if not p or not p["present"] or p["answered"] or p["excluded"]:
                continue
            if pid == exclude_pid or self._holds_active_topic(pid):
                continue
            pool.append(pid)
        return pool

    def pick_random(self, exclude_pid: str | None = None) -> str | None:
        """Roll a random eligible participant into `selected`. Returns the id,
        or None if nobody is eligible. `exclude_pid` powers 'pick someone else'
        — but if that empties the pool, we fall back to allowing them again."""
        with self.lock:
            pool = self._eligible_pool(exclude_pid)
            if not pool and exclude_pid is not None:
                pool = self._eligible_pool(None)
            if not pool:
                self.selected_pid = None
                chosen = None
            else:
                chosen = random.choice(pool)  # nosec B311 — not cryptographic
                self.selected_pid = chosen
        self.broadcast()
        return chosen

    def select_participant(self, pid: str) -> bool:
        """Manually select a specific present participant (the host included,
        since they're skipped by the random roll) so the host can hand
        themselves — or anyone — a topic. Someone who already had their turn
        this round is rejected, the same one-turn rule the random roll uses.
        So is someone currently speaking on an active topic."""
        with self.lock:
            p = self.participants.get(pid)
            if not p or not p["present"] or p["answered"] or p["excluded"]:
                return False
            if self._holds_active_topic(pid):
                return False
            self.selected_pid = pid
        self.broadcast()
        return True

    def set_excluded(self, pid: str, val: bool) -> bool:
        """Toggle whether a participant is skipped by the random roll: an opt-out
        for someone who doesn't want to be called, or a way to narrow the pool to
        people who haven't spoken. Excluded people are dropped from the roll and
        can't be manually selected either, until un-excluded. A pending selection
        on the now-excluded person is dropped so clients don't strand on the
        picking view. The flag persists across reset() (a new round doesn't
        un-opt-out anyone)."""
        with self.lock:
            p = self.participants.get(pid)
            if not p:
                return False
            p["excluded"] = bool(val)
            if p["excluded"] and self.selected_pid == pid:
                self.selected_pid = None
        self.broadcast()
        return True

    def cancel_pick(self) -> None:
        with self.lock:
            self.selected_pid = None
        self.broadcast()

    def assign(self, tid: str) -> bool:
        """Give the currently selected person an open topic. Locks the topic
        (status -> active) and makes it the focus view."""
        with self.lock:
            sid = self.selected_pid
            p = self.participants.get(sid) if sid else None
            if not p or not p["present"]:
                # No selection, or the selected person left the call before a
                # topic was handed to them — drop the stale selection.
                self.selected_pid = None
                return False
            t = self.topics.get(tid)
            if not t or t["status"] != "open":
                return False
            t["assignee"] = sid
            t["status"] = "active"
            self.active_topic_id = tid
            self.selected_pid = None
        self.broadcast()
        return True

    def mark_done(self, tid: str) -> bool:
        with self.lock:
            t = self.topics.get(tid)
            if not t:
                return False
            t["status"] = "done"
            aid = t["assignee"]
            if aid and aid in self.participants:
                self.participants[aid]["answered"] = True
            if self.active_topic_id == tid:
                self.active_topic_id = None
        self.broadcast()
        return True

    def reopen_topic(self, tid: str, reselect: bool = False) -> bool:
        """Undo an active/done topic back to open (the focus 'Back' button and
        the board 'reopen' affordance). The assignee returns to the pool. When
        `reselect` is set (the focus 'Back' case), re-select that person so we
        land back on the picking view with the topic list, ready to pick a
        different topic."""
        with self.lock:
            t = self.topics.get(tid)
            if not t:
                return False
            aid = t["assignee"]
            if aid and aid in self.participants:
                self.participants[aid]["answered"] = False
            t["assignee"] = None
            t["status"] = "open"
            if self.active_topic_id == tid:
                self.active_topic_id = None
            if reselect and aid:
                ap = self.participants.get(aid)
                # Never re-select someone who opted out after being assigned —
                # set_excluded promises they can't end up selected.
                if ap is not None and ap["present"] and not ap["excluded"]:
                    self.selected_pid = aid
        self.broadcast()
        return True

    def reset(self) -> None:
        """New round: keep the topics and the roster, but clear every
        assignment and answered flag so the same set can run again."""
        with self.lock:
            self.started_at = time.time() * 1000
            for p in self.participants.values():
                p["answered"] = False
            for t in self.topics.values():
                t["assignee"] = None
                t["status"] = "open"
            self.selected_pid = None
            self.active_topic_id = None
        self.broadcast()

    # --- demo mode ---------------------------------------------------------
    def _wipe(self) -> None:
        """Clear the whole meeting: roster, topics, and any in-flight round.
        Caller must hold self.lock."""
        self.participants.clear()
        self.order.clear()
        self.topics.clear()
        self.topic_order.clear()
        self.selected_pid = None
        self.active_topic_id = None
        self.started_at = time.time() * 1000

    def start_demo(self) -> None:
        """Load the sample meeting so a first-time host can try the flow.

        Replaces whatever is loaded with a fixed set of sample people and
        prompts and flips on the demo flag (which parks the Zoom reader).
        """
        with self.lock:
            self._wipe()
            self.demo = True
            for i, (name, is_host) in enumerate(DEMO_PARTICIPANTS):
                pid = f"d{i}"
                self._upsert(pid, name, "demo")
                self.participants[pid]["is_host"] = is_host
            for t in DEMO_TOPICS:
                self._make_topic(t["headline"], t.get("details", ""))
        self.broadcast()

    def stop_demo(self) -> None:
        """Exit the demo back to a clean slate: wipe the sample meeting and let
        the Zoom reader resume populating the roster."""
        with self.lock:
            self._wipe()
            self.demo = False
        self.broadcast()


STATE = State()


# --- HTTP + SSE ------------------------------------------------------------
# In-memory cache of static assets, keyed by path and invalidated on mtime so a
# live edit during development still shows up. Saves a disk read per request.
_STATIC_CACHE: dict[str, tuple[float, bytes]] = {}


def _read_static(path: str) -> bytes:
    mtime = os.stat(path).st_mtime
    cached = _STATIC_CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    with open(path, "rb") as f:
        body = f.read()
    _STATIC_CACHE[path] = (mtime, body)
    return body


class QuietHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that ignores benign client-disconnect errors.

    Browsers refresh, SSE clients navigate away, and tabs close: any of
    these can tear a socket while the server is mid-read. Python's stock
    `BaseHTTPRequestHandler.handle_one_request` lets the resulting
    ConnectionResetError / BrokenPipeError bubble up to the server's
    error handler, which prints a noisy traceback. These aren't bugs.
    """

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Bound per-socket timeout: a client that sends a Content-Length and then
    # stalls (or an idle keep-alive connection) frees its worker thread instead
    # of blocking forever. Comfortably above the 15s SSE keepalive interval, so
    # the long-lived /events stream is never torn by it.
    timeout = 30

    # Bound after the class body (handlers must exist as attributes first).
    _STATIC_POST: ClassVar[dict[str, Callable[[Handler], None]]]
    # The current POST's body, drained once by do_POST before dispatch.
    _body: bytes = b""

    def log_message(self, format: str, *args: Any) -> None:
        pass  # quiet

    def _json(self, code: int, obj: object) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _drain_body(self) -> bytes:
        """Read the request body exactly once, for every POST route. Leaving a
        body unread would desync the next request on a keep-alive socket, so
        this runs up front in do_POST — handlers parse the stash via _read_json.
        """
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return b""
        if n <= 0:
            return b""
        if n > 1024 * 1024:  # 1MB limit
            # Body is left unread; close the connection so the unconsumed
            # bytes can't desync the next request on this keep-alive socket.
            self.close_connection = True
            return b""
        return self.rfile.read(n)

    def _read_json(self) -> dict[str, Any]:
        try:
            data = json.loads(self._body or b"{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _origin_ok(self) -> bool:
        """CSRF guard for state-changing POSTs. A browser attaches an Origin
        header to cross-site requests; reject any whose authority doesn't match
        the Host we were reached on. Non-browser clients (curl, tests) send no
        Origin and are allowed."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).netloc == self.headers.get("Host", "")

    def _serve_file(self, path: str, ctype: str, missing: tuple[int, str]) -> None:
        try:
            body = _read_static(path)
        except FileNotFoundError:
            return self._json(missing[0], {"error": missing[1]})
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        # Route on the path component only, so a query string (e.g. a
        # cache-buster like /app.js?v=1) still matches the static allowlist.
        path = urlparse(self.path).path
        if path == "/" or path.startswith("/index"):
            return self._serve_file(
                INDEX_HTML, "text/html; charset=utf-8", (500, "index.html missing")
            )

        asset = STATIC_FILES.get(path)
        if asset is not None:
            return self._serve_file(asset[0], asset[1], (404, "not found"))

        if path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q: queue.Queue[str] = queue.Queue()
            with STATE.lock:
                STATE.clients.add(q)
            try:
                self.wfile.write(
                    ("data: " + json.dumps(STATE.snapshot()) + "\n\n").encode()
                )
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(msg.encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except BrokenPipeError, ConnectionResetError, OSError:
                pass
            finally:
                with STATE.lock:
                    STATE.clients.discard(q)
            return

        self._json(404, {"error": "not found"})

    TOPIC_ROUTE = re.compile(r"^/api/topic/([^/]+)/(edit|remove|done|reopen|assign)$")
    PARTICIPANT_ROUTE = re.compile(r"^/api/participant/([^/]+)/(host|remove|exclude)$")

    def do_POST(self) -> None:
        # Drain the body up front so every route — including 403/404 responses
        # and handlers that ignore their body — leaves the keep-alive socket
        # positioned at the next request.
        self._body = self._drain_body()
        if not self._origin_ok():
            return self._json(403, {"error": "cross-origin request rejected"})
        # Route on the path component only, same as do_GET, so a query string
        # (e.g. a cache-buster) can't turn a valid action into a 404.
        path = urlparse(self.path).path
        handler = self._STATIC_POST.get(path)
        if handler:
            return handler(self)
        m = self.TOPIC_ROUTE.match(path)
        if m:
            return self._topic_action(m.group(1), m.group(2))
        m = self.PARTICIPANT_ROUTE.match(path)
        if m:
            return self._participant_action(m.group(1), m.group(2))
        self._json(404, {"error": "not found"})

    # --- participant endpoints --------------------------------------------
    def _post_add_participant(self) -> None:
        name = str(self._read_json().get("name", "")).strip()
        if not name:
            return self._json(400, {"error": "name required"})
        STATE.add_manual(name)
        self._json(200, {"ok": True})

    def _participant_action(self, pid: str, action: str) -> None:
        if action == "host":
            ok = STATE.set_host(pid, bool(self._read_json().get("host")))
        elif action == "exclude":
            ok = STATE.set_excluded(pid, bool(self._read_json().get("excluded")))
        else:  # remove
            STATE.remove(pid)
            ok = True
        self._json(200 if ok else 404, {"ok": ok})

    # --- topic endpoints ---------------------------------------------------
    def _post_add_topic(self) -> None:
        body = self._read_json()
        tid = STATE.add_topic(body.get("headline", ""), body.get("details", ""))
        if tid is None:
            return self._json(400, {"error": "headline required"})
        self._json(200, {"ok": True, "id": tid})

    def _post_topics(self) -> None:
        body = self._read_json()
        topics = body.get("topics", [])
        if not isinstance(topics, list):
            return self._json(400, {"error": "topics must be a list"})
        added = STATE.add_topics(topics, replace=bool(body.get("replace", False)))
        self._json(200, {"ok": True, "added": added})

    def _topic_action(self, tid: str, action: str) -> None:
        if action == "edit":
            body = self._read_json()
            ok = STATE.edit_topic(
                tid, body.get("headline", ""), body.get("details", "")
            )
        elif action == "remove":
            ok = STATE.remove_topic(tid)
        elif action == "done":
            ok = STATE.mark_done(tid)
        elif action == "reopen":
            body = self._read_json()
            ok = STATE.reopen_topic(tid, reselect=bool(body.get("reselect", False)))
        else:  # assign
            ok = STATE.assign(tid)
        self._json(200 if ok else 400, {"ok": ok})

    # --- selection endpoints ----------------------------------------------
    def _post_pick(self) -> None:
        raw = self._read_json().get("exclude")
        exclude = str(raw) if raw else None
        pid = STATE.pick_random(exclude)
        self._json(200, {"ok": pid is not None, "selected": pid})

    def _post_select(self) -> None:
        pid = str(self._read_json().get("pid", "")).strip()
        ok = STATE.select_participant(pid) if pid else False
        self._json(200 if ok else 404, {"ok": ok})

    def _post_cancel_pick(self) -> None:
        STATE.cancel_pick()
        self._json(200, {"ok": True})

    def _post_reset(self) -> None:
        STATE.reset()
        self._json(200, {"ok": True})

    # --- demo mode endpoints ----------------------------------------------
    def _post_demo_start(self) -> None:
        STATE.start_demo()
        self._json(200, {"ok": True})

    def _post_demo_stop(self) -> None:
        STATE.stop_demo()
        self._json(200, {"ok": True})


# Bind route table after the class body so handlers exist as attributes.
Handler._STATIC_POST = {
    "/api/participant": Handler._post_add_participant,
    "/api/topic": Handler._post_add_topic,
    "/api/topics": Handler._post_topics,
    "/api/pick": Handler._post_pick,
    "/api/select": Handler._post_select,
    "/api/pick/cancel": Handler._post_cancel_pick,
    "/api/reset": Handler._post_reset,
    "/api/demo/start": Handler._post_demo_start,
    "/api/demo/stop": Handler._post_demo_stop,
}


# --- Reader poller thread --------------------------------------------------
def poller(args: argparse.Namespace, exclude_re: re.Pattern[str]) -> None:
    pat_warned = False
    while True:
        try:
            people = read_zoom_participants(args, exclude_re)
            if people is None:
                # Zoom isn't running (no process / no window) — leave the roster
                # untouched; don't mistake "can't read" for "nobody's here".
                if not pat_warned:
                    sys.stderr.write(
                        "[reader] Zoom not running yet; will keep checking.\n"
                    )
                    pat_warned = True
            elif people:
                pat_warned = False
                STATE.sync_participants(people)
            else:
                # Zoom is up but the read came back empty. During a live meeting
                # the Participants panel is never legitimately empty, so an empty
                # read almost always means "can't see the panel" — it's collapsed,
                # or screen-sharing the board has moved/closed it — not "everyone
                # left". Treat it like Zoom-not-running and leave the roster
                # intact, so sharing the board doesn't strand the host on an empty
                # room. A genuine departure is still caught on the next readable
                # poll, where the missing name is simply absent from a non-empty
                # list (sync_participants -> _mark_missing_as_left).
                pat_warned = False
        except Exception as e:
            sys.stderr.write(f"[reader] read error: {e}\n")
        time.sleep(args.interval)


def _decide_reader_mode(no_ax: bool) -> bool:
    """Decide whether to start the auto-reader thread.

    Returns True if a per-platform accessibility backend is available and
    permission has been granted; False (with a stderr explainer) otherwise.
    """
    if no_ax:
        return False
    if sys.platform == "darwin":
        if not AX_AVAILABLE:
            sys.stderr.write(
                "\n[ax] pyobjc not available. Manual-only mode.\n"
                "     For auto-reading: uv sync\n"
            )
            return False
        if not AXIsProcessTrusted():
            sys.stderr.write(
                "\n[ax] Accessibility permission NOT granted. Running in "
                "manual-only mode.\n"
                "     Grant it in System Settings > Privacy & Security > "
                "Accessibility\n"
                "     to the app you run this from (Terminal/iTerm), then "
                "reopen it.\n"
            )
            return False
        return True
    if sys.platform == "win32":
        if not UIA_AVAILABLE:
            sys.stderr.write(
                "\n[uia] uiautomation not available. Manual-only mode.\n"
                "     For auto-reading: uv sync\n"
            )
            return False
        return True
    sys.stderr.write(
        "\n[reader] Auto-read is only supported on macOS and Windows. "
        "Running in manual-only mode.\n"
    )
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--bundle", default=DEFAULT_BUNDLE)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--anchor-regex", default="participant")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--min-len", type=int, default=2)
    ap.add_argument(
        "--no-ax", action="store_true", help="manual entry only; do not read Zoom"
    )
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    exclude_re = build_exclude_re(
        DEFAULT_EXCLUDE + [x.strip() for x in args.exclude.split(",") if x.strip()]
    )

    reader_on = _decide_reader_mode(args.no_ax)
    if reader_on:
        threading.Thread(target=poller, args=(args, exclude_re), daemon=True).start()

    mode = (
        f"AUTO (reading Zoom every {args.interval:g}s) + manual"
        if reader_on
        else "MANUAL only"
    )
    srv = QuietHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\n  Table Topics board:  http://localhost:{args.port}")
    print(f"  Mode: {mode}")
    print("  Open the URL and screen-share that tab. Ctrl-C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
