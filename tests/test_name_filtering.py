"""Tests for the pure name-cleaning / filtering helpers in board.py.

These helpers are vendored unchanged from the sibling `zoom-icebreaker`
project, so the cases mirror that project's `test_name_filtering.py`.
"""

import argparse

import pytest

import board
from board import (
    CHAT_HINT_RE,
    DEFAULT_EXCLUDE,
    HOST_DETECT,
    _filter_and_dedupe,
    _uia_hay,
    build_exclude_re,
    clean_name,
    looks_like_name,
)


class TestCleanName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Alice", "Alice"),
            ("  Alice  ", "Alice"),
            ("Alice (host)", "Alice"),
            ("Alice (Host)", "Alice"),
            ("Alice (co-host)", "Alice"),
            ("Alice (cohost)", "Alice"),
            ("Alice (me)", "Alice"),
            ("Alice (you)", "Alice"),
            ("Alice (guest)", "Alice"),
            ("Alice (host, me)", "Alice"),
            ("Alice (cohost, me)", "Alice"),
            # Zoom hyphenates freely; without this strip the leftover "co-host"
            # word would match the exclude list and drop the participant.
            ("Alice (co-host, me)", "Alice"),
            ("Alice (Co-host, me)", "Alice"),
            ("Alice (guest, you)", "Alice"),
            # Webinar roles. These MUST be stripped: "panelist" is itself an
            # entry in DEFAULT_EXCLUDE, so a leftover "(Panelist)" makes
            # looks_like_name drop the attendee from the roster entirely.
            ("Alice (Panelist)", "Alice"),
            ("Alice (panelist)", "Alice"),
            ("Alice (Attendee)", "Alice"),
            ("Alice (Co-host, Panelist)", "Alice"),
            ("Alice (Host, Attendee)", "Alice"),
            # Zoom pads inconsistently between versions.
            ("Alice ( host )", "Alice"),
            # Trailing role-word without parens is also stripped.
            ("Alice host", "Alice"),
            ("Alice cohost", "Alice"),
            ("Alice  guest", "Alice"),
        ],
    )
    def test_strips_role_annotations(self, raw, expected):
        assert clean_name(raw) == expected

    @pytest.mark.parametrize(
        "raw", ["Ann (he/him)", "Ann (she/her)", "Ann (they/them)"]
    )
    def test_preserves_pronouns(self, raw):
        # Pronouns contain no role word, so the annotation regex must leave
        # them alone — they are part of how someone chose to be addressed.
        assert clean_name(raw) == raw

    def test_webinar_panelist_survives_the_exclude_list(self):
        # Regression: the end-to-end path that silently emptied the roster in
        # a webinar. Strip must happen before looks_like_name sees the name.
        exclude_re = build_exclude_re(DEFAULT_EXCLUDE)
        assert looks_like_name(clean_name("Alice (Panelist)"), exclude_re, 2)

    def test_preserves_internal_role_words(self):
        # Only trailing role words are stripped.
        assert clean_name("Hosting Hostetler") == "Hosting Hostetler"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Joined (1)", "Joined"),
            ("Joined (12)", "Joined"),
            ("Not joined (0)", "Not joined"),
            ("Alice (3)", "Alice"),
        ],
    )
    def test_strips_trailing_paren_counts(self, raw, expected):
        # Chat-panel section headers like "Joined (12)" carry a count
        # in parens; strip it so the exclude list can catch the header.
        assert clean_name(raw) == expected

    def test_trims_trailing_separators(self):
        assert clean_name("Alice,") == "Alice"
        assert clean_name("Alice - ") == "Alice"

    def test_empty_input(self):
        assert clean_name("") == ""
        assert clean_name("   ") == ""


class TestLooksLikeName:
    @pytest.fixture
    def exclude_re(self):
        return build_exclude_re(DEFAULT_EXCLUDE)

    @pytest.mark.parametrize(
        "name",
        ["Alice", "Bob Smith", "X Y", "Renée Müller", "Jean-Luc"],
    )
    def test_accepts_real_names(self, name, exclude_re):
        assert looks_like_name(name, exclude_re, min_len=2)

    def test_rejects_too_short(self, exclude_re):
        assert not looks_like_name("A", exclude_re, min_len=2)

    def test_rejects_excluded_terms(self, exclude_re):
        assert not looks_like_name("Mute", exclude_re, min_len=2)
        assert not looks_like_name("Participants", exclude_re, min_len=2)
        assert not looks_like_name("Start Video", exclude_re, min_len=2)

    def test_rejects_chat_panel_chrome(self, exclude_re):
        # These are post-COUNT_TAIL strings; the count strip happens in
        # clean_name, but the chrome words themselves must also be excluded.
        assert not looks_like_name("Joined", exclude_re, min_len=2)
        assert not looks_like_name("Not joined", exclude_re, min_len=2)
        assert not looks_like_name("Who can see your messages", exclude_re, min_len=2)
        # Zoom's delivery indicator: "1 participant(s) sent..."
        # `(` is a regex word boundary, so \bparticipant\b matches.
        assert not looks_like_name("1 participant(s) sent...", exclude_re, min_len=2)
        assert not looks_like_name("1 panelist sent", exclude_re, min_len=2)

    def test_rejects_excluded_as_substring_word(self, exclude_re):
        # "host" alone is excluded, but it must match as a whole word.
        assert not looks_like_name("host", exclude_re, min_len=2)
        # "Hostetler" should still pass — it contains "host" but not as a word.
        assert looks_like_name("Hostetler", exclude_re, min_len=2)

    def test_rejects_punctuation_or_digits_only(self, exclude_re):
        assert not looks_like_name("123", exclude_re, min_len=2)
        assert not looks_like_name("---", exclude_re, min_len=2)
        assert not looks_like_name("__", exclude_re, min_len=2)

    def test_rejects_overly_long_strings(self, exclude_re):
        assert not looks_like_name("x" * 61, exclude_re, min_len=2)
        assert looks_like_name("x" * 60, exclude_re, min_len=2)

    def test_min_len_is_inclusive(self, exclude_re):
        assert looks_like_name("Al", exclude_re, min_len=2)
        assert not looks_like_name("Al", exclude_re, min_len=3)


class TestBuildExcludeRe:
    def test_matches_whole_words_case_insensitive(self):
        r = build_exclude_re(["mute", "raise hand"])
        assert r.search("Mute")
        assert r.search("please raise hand now")
        assert not r.search("Hammer")
        assert not r.search("commuter")  # "mute" is a substring; \b prevents match

    def test_orders_longest_first(self):
        # If "host" came first, "co-host" would never get a chance to match —
        # but we sort by length descending. The pattern just needs to match the
        # longer term anywhere in the string.
        r = build_exclude_re(["host", "co-host"])
        assert r.search("co-host")
        assert r.search("host")

    def test_escapes_regex_metacharacters(self):
        r = build_exclude_re(["a.b", "x+y"])
        assert r.search("a.b")
        assert not r.search("axb")  # the "." was escaped
        assert r.search("x+y")

    def test_deduplicates(self):
        # Duplicates should not blow up or cause issues.
        r = build_exclude_re(["mute", "mute", "MUTE"])
        assert r.search("mute")

    def test_terms_with_edge_punctuation_still_match(self):
        # \b next to a non-word edge can never match, so boundaries are only
        # anchored where the term's edge is a word character — a user-supplied
        # --exclude "(external)" must actually fire.
        r = build_exclude_re(["(external)"])
        assert r.search("Panel label (external)")
        assert r.search("(external)")
        # The inner word boundary rule still holds for word-edged terms.
        r = build_exclude_re(["mute"])
        assert not r.search("commuter")


class TestHostDetect:
    @pytest.mark.parametrize(
        "raw",
        [
            "Alice (host)",
            "Alice (Host)",
            "Alice (host, me)",
            "Alice (host,me)",
            "Alice (HOST, ME)",
        ],
    )
    def test_matches_primary_host_markers(self, raw):
        assert HOST_DETECT.search(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "Alice (co-host)",
            "Alice (cohost)",
            "Alice (cohost, me)",
            "Alice (me)",
            "Alice (guest)",
            "Alice",
        ],
    )
    def test_does_not_match_non_host_markers(self, raw):
        assert not HOST_DETECT.search(raw)


class TestFilterAndDedupe:
    @pytest.fixture
    def exclude_re(self):
        return build_exclude_re(DEFAULT_EXCLUDE)

    def test_cleans_filters_and_dedupes(self, exclude_re):
        raw = [
            "Alice (host)",
            "Bob (me)",
            "Mute",  # excluded chrome
            "alice",  # case-insensitive dupe of Alice
            "",  # empty after cleaning
        ]
        people = _filter_and_dedupe(raw, exclude_re, min_len=2)
        names = [p["name"] for p in people]
        assert names == ["Alice", "Bob"]

    def test_detects_host_from_raw_before_cleaning(self, exclude_re):
        # Host detection runs on the raw text; "(host)" is stripped by
        # clean_name, so the flag must be captured beforehand.
        people = _filter_and_dedupe(["Alice (host)", "Bob"], exclude_re, min_len=2)
        by_name = {p["name"]: p for p in people}
        assert by_name["Alice"]["is_host"] is True
        assert by_name["Bob"]["is_host"] is False

    def test_cohost_is_not_flagged_as_host(self, exclude_re):
        people = _filter_and_dedupe(["Carol (co-host)"], exclude_re, min_len=2)
        assert people == [{"name": "Carol", "is_host": False}]

    def test_host_flag_preserved_when_bare_name_seen_first(self, exclude_re):
        # "Alice" (no marker) before "Alice (host)" must still flag Alice as
        # host — the later host token can't be dropped wholesale.
        people = _filter_and_dedupe(["Alice", "Alice (host)"], exclude_re, min_len=2)
        assert people == [{"name": "Alice", "is_host": True}]


class _FakeUIAElement:
    """Minimal stand-in for a UIA element: just the attrs the detector reads."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)


class TestChatAnchorDetection:
    @pytest.mark.parametrize(
        "text",
        ["Chat", "chat", "Meeting Chat", "Chat panel"],
    )
    def test_chat_hint_matches_whole_word(self, text):
        assert CHAT_HINT_RE.search(text)

    @pytest.mark.parametrize(
        "text",
        ["Participants", "Chatham House", "Chatterjee"],
    )
    def test_chat_hint_ignores_substrings_and_non_chat(self, text):
        # \bchat\b must match "chat" as a word, not inside "Chatterjee".
        assert not CHAT_HINT_RE.search(text)

    # Chat rejection searches the same joined haystack anchor matching uses
    # (_uia_hay), so a hint in any harvested attribute rejects the anchor.
    def test_uia_anchor_flagged_when_any_attr_mentions_chat(self):
        assert CHAT_HINT_RE.search(_uia_hay(_FakeUIAElement(Name="Chat")))
        assert CHAT_HINT_RE.search(
            _uia_hay(_FakeUIAElement(AutomationId="meeting chat"))
        )
        assert CHAT_HINT_RE.search(
            _uia_hay(_FakeUIAElement(LocalizedControlType="chat list"))
        )

    def test_uia_anchor_camelcase_id_is_not_caught(self):
        # CHAT_HINT_RE is \bchat\b, so identifier-style values with no word
        # boundary ("ChatPanel") are NOT flagged — only "chat" as a word is.
        assert not CHAT_HINT_RE.search(
            _uia_hay(_FakeUIAElement(AutomationId="ChatPanel"))
        )

    def test_uia_anchor_not_flagged_for_participant_panel(self):
        el = _FakeUIAElement(Name="Participants (3)", AutomationId="ParticipantsList")
        assert not CHAT_HINT_RE.search(_uia_hay(el))


def _ax_node(role="AXGroup", text=None, identifier=None, children=()):
    """A fake AX element as a plain attribute dict (see `_fake_attr`)."""
    return {
        "AXRole": role,
        "AXValue": text,
        "AXIdentifier": identifier,
        "AXChildren": list(children),
    }


def _fake_attr(el, name):
    return el.get(name)


class TestCollectTextsPruning:
    """`_collect_texts` must skip the panel's non-participant rows.

    Zoom's participants panel lists people who were invited but never joined
    under a "Not joined (N)" header, each with their RSVP as a child node. A
    flat harvest turns those into roster entries, and because the board picks
    a speaker at random it can then spotlight someone who is not in the
    meeting -- or "Accepted".
    """

    @pytest.fixture
    def patched(self, monkeypatch):
        monkeypatch.setattr(board, "_attr", _fake_attr)

    def test_harvests_joined_participants(self, patched):
        tree = _ax_node(
            children=[
                _ax_node(
                    role="AXCell",
                    identifier="ZMHCTableItemType_PANELIST",
                    children=[_ax_node(role="AXStaticText", text="Alice")],
                )
            ]
        )
        out = []
        board._collect_texts(tree, out)
        assert "Alice" in out

    @pytest.mark.parametrize(
        "identifier,label,child",
        [
            ("ZMHCTableItemType_Invitee", "Emmanuel Arinze", "Accepted"),
            ("ZMHCTableItemType_Invitee_Group", "Not joined (1)", "Declined"),
            ("ZMHCTableItemType_PANELIST_Group", "Joined (2)", "Awaiting response"),
        ],
    )
    def test_prunes_non_participant_rows(self, patched, identifier, label, child):
        tree = _ax_node(
            children=[
                _ax_node(
                    role="AXCell",
                    text=label,
                    identifier=identifier,
                    children=[_ax_node(role="AXStaticText", text=child)],
                )
            ]
        )
        out = []
        board._collect_texts(tree, out)
        # Pruned, not merely skipped: the RSVP hangs BELOW the row, so
        # descending into it would harvest the child anyway.
        assert out == []

    def test_unknown_identifier_still_harvested(self, patched):
        # If Zoom renames these ids the reader must degrade to its old
        # behaviour rather than silently reporting an empty meeting.
        tree = _ax_node(role="AXStaticText", text="Alice", identifier="SomethingNew")
        out = []
        board._collect_texts(tree, out)
        assert out == ["Alice"]


class TestNoAnchorMeansNoParticipants:
    """With no participants panel, harvesting the whole app scrapes Zoom's own
    chrome -- every toolbar button is an AXButton with a description, and
    AXButton is a text role. Verified against a live Zoom: 10 real people
    became 58 entries including "Giphy", "Send", "History" and "Upgrade".
    """

    @pytest.fixture
    def args(self):
        return argparse.Namespace(
            bundle="us.zoom.xos",
            anchor_regex="participant",
            min_len=2,
            debug=False,
            exclude="",
        )

    @pytest.fixture
    def exclude_re(self):
        return build_exclude_re(DEFAULT_EXCLUDE)

    def test_ax_reader_reports_none_without_an_anchor(
        self, monkeypatch, args, exclude_re
    ):
        monkeypatch.setattr(board, "_find_pid", lambda _b: 123)
        monkeypatch.setattr(
            board, "AXUIElementCreateApplication", lambda _p: "app", raising=False
        )
        monkeypatch.setattr(board, "_collect_anchors", lambda *_a: None)
        monkeypatch.setattr(
            board,
            "_collect_texts",
            lambda *_a: pytest.fail("must not harvest without an anchor"),
        )
        assert board._read_zoom_participants_ax(args, exclude_re) == []

    def test_ax_reader_returns_none_when_zoom_is_not_running(
        self, monkeypatch, args, exclude_re
    ):
        # Distinct from []: "Zoom isn't running" must not be confused with
        # "Zoom is up but the panel is hidden".
        monkeypatch.setattr(board, "_find_pid", lambda _b: None)
        assert board._read_zoom_participants_ax(args, exclude_re) is None

    def test_ax_reader_harvests_only_the_anchored_subtrees(
        self, monkeypatch, args, exclude_re
    ):
        harvested = []
        monkeypatch.setattr(board, "_find_pid", lambda _b: 123)
        monkeypatch.setattr(
            board, "AXUIElementCreateApplication", lambda _p: "app", raising=False
        )
        monkeypatch.setattr(
            board, "_collect_anchors", lambda _el, _p, found: found.append("panel")
        )

        def fake_texts(root, out):
            harvested.append(root)
            out.append("Alice")

        monkeypatch.setattr(board, "_collect_texts", fake_texts)
        people = board._read_zoom_participants_ax(args, exclude_re)
        assert harvested == ["panel"]  # the anchor, never the app root
        assert [p["name"] for p in people] == ["Alice"]

    def test_uia_reader_reports_none_without_an_anchor(
        self, monkeypatch, args, exclude_re
    ):
        monkeypatch.setattr(board, "_uia_zoom_windows", lambda: ["win"])
        monkeypatch.setattr(board, "_uia_collect_anchors", lambda *_a: None)
        monkeypatch.setattr(
            board,
            "_uia_collect_texts",
            lambda *_a: pytest.fail("must not harvest without an anchor"),
        )
        assert board._read_zoom_participants_uia(args, exclude_re) == []

    def test_uia_reader_harvests_only_the_anchored_subtrees(
        self, monkeypatch, args, exclude_re
    ):
        harvested = []
        monkeypatch.setattr(board, "_uia_zoom_windows", lambda: ["win"])
        monkeypatch.setattr(
            board, "_uia_collect_anchors", lambda _el, _p, found: found.append("panel")
        )

        def fake_texts(root, out):
            harvested.append(root)
            out.append("Alice")

        monkeypatch.setattr(board, "_uia_collect_texts", fake_texts)
        people = board._read_zoom_participants_uia(args, exclude_re)
        assert harvested == ["panel"]  # the anchor, never the window root
        assert [p["name"] for p in people] == ["Alice"]

    def test_uia_reader_returns_none_when_zoom_is_not_running(
        self, monkeypatch, args, exclude_re
    ):
        monkeypatch.setattr(board, "_uia_zoom_windows", lambda: [])
        assert board._read_zoom_participants_uia(args, exclude_re) is None
