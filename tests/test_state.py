"""Tests for the State class in board.py."""

import random

import pytest

from board import DEMO_PARTICIPANTS, DEMO_TOPICS, State


def _names(snapshot):
    return [p["name"] for p in snapshot["participants"]]


def _by_name(state, name):
    """Return the participant dict matching `name` (case-insensitive)."""
    with state.lock:
        for p in state.participants.values():
            if p["name"].lower() == name.lower():
                return p
    raise KeyError(name)


def _pid_of(state, name):
    return _by_name(state, name)["id"]


def _topic_by_headline(snapshot, headline):
    for t in snapshot["topics"]:
        if t["headline"] == headline:
            return t
    raise KeyError(headline)


@pytest.fixture
def state():
    return State()


class TestSyncParticipants:
    def test_adds_new_participants_in_order(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        assert _names(state.snapshot()) == ["Alice", "Bob"]

    def test_ignores_blank_names(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "  ", "is_host": False},
                {"name": "", "is_host": False},
            ]
        )
        assert _names(state.snapshot()) == ["Alice"]

    def test_is_idempotent_for_same_input(self, state):
        people = [{"name": "Alice", "is_host": False}]
        assert state.sync_participants(people) is True
        # Second sync with identical input shouldn't claim a change.
        assert state.sync_participants(people) is False

    def test_marks_missing_as_left_then_returning_makes_present(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        # Bob disappears from panel.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        bob = _by_name(state, "Bob")
        assert bob["present"] is False
        assert bob["leftTime"] is not None
        # Bob comes back.
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        bob = _by_name(state, "Bob")
        assert bob["present"] is True
        assert bob["leftTime"] is None

    def test_manual_entries_are_not_marked_left_when_missing_from_ax(self, state):
        # Manual entries get id prefix "m" so the AX-tracking pass leaves them.
        state.add_manual("Carol")
        state.sync_participants([{"name": "Alice", "is_host": False}])
        carol = _by_name(state, "Carol")
        assert carol["present"] is True
        assert carol["leftTime"] is None

    def test_selected_participant_clears_when_they_leave(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        state.select_participant(_pid_of(state, "Bob"))
        assert state.selected_pid is not None
        # Bob drops off the auto-read panel; the pending selection clears.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        assert state.selected_pid is None

    def test_empty_sync_marks_present_ax_people_as_left(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        # An empty read (Zoom up, nobody detected) clears the AX roster — the
        # poller debounces this, but the State behavior must be correct.
        state.sync_participants([])
        assert _by_name(state, "Alice")["present"] is False
        assert _by_name(state, "Bob")["present"] is False


class TestHostHandling:
    def test_host_is_pinned_to_first_slot(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": True},
                {"name": "Carol", "is_host": False},
            ]
        )
        assert _names(state.snapshot())[0] == "Bob"

    def test_most_recent_host_wins(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": True},
                {"name": "Bob", "is_host": False},
            ]
        )
        assert _by_name(state, "Alice")["is_host"]
        # Host changes to Bob.
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": True},
            ]
        )
        assert _by_name(state, "Bob")["is_host"]
        assert not _by_name(state, "Alice")["is_host"]
        assert _names(state.snapshot())[0] == "Bob"

    def test_only_one_host_at_a_time(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": True},
                {"name": "Bob", "is_host": True},
            ]
        )
        hosts = [p["name"] for p in state.snapshot()["participants"] if p["is_host"]]
        assert len(hosts) == 1
        # The "last write wins" — Bob came second, so Bob is the host.
        assert hosts == ["Bob"]

    def test_set_host_manually_promotes_and_pins(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
                {"name": "Carol", "is_host": False},
            ]
        )
        carol_pid = _pid_of(state, "Carol")
        assert state.set_host(carol_pid, True) is True
        snap = state.snapshot()
        assert snap["participants"][0]["name"] == "Carol"
        assert snap["participants"][0]["is_host"]

    def test_set_host_false_demotes(self, state):
        state.sync_participants([{"name": "Alice", "is_host": True}])
        pid = _pid_of(state, "Alice")
        state.set_host(pid, False)
        assert not _by_name(state, "Alice")["is_host"]

    def test_set_host_on_unknown_pid_returns_false(self, state):
        assert state.set_host("nope", True) is False


class TestTopics:
    def test_add_topic_returns_id_and_strips_whitespace(self, state):
        tid = state.add_topic("  What is courage?  ", "  some details  ")
        assert tid is not None
        snap = state.snapshot()
        t = _topic_by_headline(snap, "What is courage?")
        assert t["id"] == tid
        assert t["details"] == "some details"
        assert t["status"] == "open"
        assert t["assignee"] is None

    def test_add_topic_blank_headline_returns_none(self, state):
        assert state.add_topic("   ") is None
        assert state.add_topic("") is None
        assert state.snapshot()["topics"] == []

    def test_topic_ids_are_monotonic(self, state):
        t1 = state.add_topic("One")
        t2 = state.add_topic("Two")
        assert t1 == "t1"
        assert t2 == "t2"

    def test_add_topics_appends_in_bulk(self, state):
        state.add_topic("First")
        added = state.add_topics(
            [
                {"headline": "Second", "details": "d2"},
                {"headline": "Third"},
            ]
        )
        assert added == 2
        headlines = [t["headline"] for t in state.snapshot()["topics"]]
        assert headlines == ["First", "Second", "Third"]

    def test_add_topics_skips_blank_headlines(self, state):
        added = state.add_topics(
            [
                {"headline": "Real"},
                {"headline": "   "},
                {"details": "no headline"},
                "not a dict",
            ]
        )
        assert added == 1
        assert [t["headline"] for t in state.snapshot()["topics"]] == ["Real"]

    def test_add_topics_replace_clears_existing_first(self, state):
        state.add_topic("Old")
        added = state.add_topics([{"headline": "New"}], replace=True)
        assert added == 1
        assert [t["headline"] for t in state.snapshot()["topics"]] == ["New"]

    def test_add_topics_replace_clears_active_topic(self, state):
        state.add_topic("Topic")
        state.add_manual("Alice")
        state.select_participant(_pid_of(state, "Alice"))
        tid = state.snapshot()["topics"][0]["id"]
        state.assign(tid)
        assert state.active_topic_id == tid
        state.add_topics([{"headline": "Fresh"}], replace=True)
        assert state.active_topic_id is None

    def test_add_topics_replace_clears_pending_selection(self, state):
        # Clearing the topic set mid-roll must not strand a selection that can
        # no longer be assigned to anything.
        state.add_manual("Alice")
        state.add_topic("Old")
        state.select_participant(_pid_of(state, "Alice"))
        assert state.selected_pid is not None
        state.add_topics([{"headline": "New"}], replace=True)
        assert state.selected_pid is None

    def test_edit_topic_unknown_returns_false(self, state):
        assert state.edit_topic("nope", "Headline", "details") is False

    def test_edit_topic_blank_headline_returns_false(self, state):
        tid = state.add_topic("Original")
        assert state.edit_topic(tid, "   ", "details") is False
        # Original is untouched.
        assert state.snapshot()["topics"][0]["headline"] == "Original"

    def test_edit_topic_success_updates(self, state):
        tid = state.add_topic("Original", "old details")
        assert state.edit_topic(tid, "  Updated  ", "  new details  ") is True
        t = state.snapshot()["topics"][0]
        assert t["headline"] == "Updated"
        assert t["details"] == "new details"

    def test_remove_topic_unknown_returns_false(self, state):
        assert state.remove_topic("nope") is False

    def test_remove_topic_success(self, state):
        tid = state.add_topic("Doomed")
        assert state.remove_topic(tid) is True
        assert state.snapshot()["topics"] == []

    def test_remove_active_topic_clears_active_id(self, state):
        state.add_manual("Alice")
        state.select_participant(_pid_of(state, "Alice"))
        tid = state.add_topic("Topic")
        state.assign(tid)
        assert state.active_topic_id == tid
        assert state.remove_topic(tid) is True
        assert state.active_topic_id is None


class TestPickRandom:
    def _seed_pool(self, state):
        state.sync_participants(
            [
                {"name": "Host", "is_host": True},
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
                {"name": "Carol", "is_host": False},
            ]
        )

    def test_only_eligible_get_chosen_and_never_host(self, state):
        self._seed_pool(state)
        host_pid = _pid_of(state, "Host")
        chosen = {state.pick_random() for _ in range(50)}
        assert host_pid not in chosen
        # Every chosen id resolves to a non-host present participant.
        for pid in chosen:
            p = state.participants[pid]
            assert p["is_host"] is False
            assert p["present"] is True
            assert p["answered"] is False

    def test_answered_are_excluded(self, state):
        self._seed_pool(state)
        # Mark everyone but Alice answered.
        for n in ("Bob", "Carol"):
            _by_name(state, n)["answered"] = True
        random.seed(0)
        for _ in range(20):
            assert state.pick_random() == _pid_of(state, "Alice")

    def test_not_present_are_excluded(self, state):
        self._seed_pool(state)
        # Only Alice stays in the panel; Bob and Carol leave.
        state.sync_participants(
            [
                {"name": "Host", "is_host": True},
                {"name": "Alice", "is_host": False},
            ]
        )
        random.seed(0)
        for _ in range(20):
            assert state.pick_random() == _pid_of(state, "Alice")

    def test_empty_pool_returns_none_and_clears_selection(self, state):
        state.sync_participants([{"name": "Host", "is_host": True}])
        # Pre-seed a selection so we can confirm it gets cleared.
        state.selected_pid = "stale"
        assert state.pick_random() is None
        assert state.selected_pid is None

    def test_exclude_pid_avoids_that_pid_when_others_exist(self, state):
        self._seed_pool(state)
        alice = _pid_of(state, "Alice")
        for _ in range(30):
            assert state.pick_random(exclude_pid=alice) != alice

    def test_exclude_pid_falls_back_when_pool_would_empty(self, state):
        # Only one eligible person; excluding them must still re-pick them.
        state.sync_participants(
            [
                {"name": "Host", "is_host": True},
                {"name": "Solo", "is_host": False},
            ]
        )
        solo = _pid_of(state, "Solo")
        assert state.pick_random(exclude_pid=solo) == solo
        assert state.selected_pid == solo

    def test_pick_sets_selected_pid(self, state):
        self._seed_pool(state)
        random.seed(42)
        chosen = state.pick_random()
        assert state.selected_pid == chosen


class TestSelectParticipant:
    def test_selects_present_person(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        assert state.select_participant(pid) is True
        assert state.selected_pid == pid

    def test_host_may_be_selected(self, state):
        state.sync_participants([{"name": "Host", "is_host": True}])
        host_pid = _pid_of(state, "Host")
        assert state.select_participant(host_pid) is True
        assert state.selected_pid == host_pid

    def test_unknown_pid_returns_false(self, state):
        assert state.select_participant("nope") is False

    def test_not_present_returns_false(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        # Bob leaves the panel.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        bob = _pid_of(state, "Bob")
        assert state.select_participant(bob) is False

    def test_answered_person_cannot_be_selected(self, state):
        # Manual select honors the same one-turn rule as the random roll.
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        _by_name(state, "Alice")["answered"] = True
        assert state.select_participant(pid) is False
        assert state.selected_pid is None


class TestCancelPick:
    def test_clears_selected_pid(self, state):
        state.add_manual("Alice")
        state.select_participant(_pid_of(state, "Alice"))
        assert state.selected_pid is not None
        state.cancel_pick()
        assert state.selected_pid is None


class TestAssign:
    def _setup(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("A topic")
        return pid, tid

    def test_assign_success(self, state):
        pid, tid = self._setup(state)
        state.select_participant(pid)
        assert state.assign(tid) is True
        t = state.snapshot()["topics"][0]
        assert t["status"] == "active"
        assert t["assignee"] == {"id": pid, "name": "Alice"}
        assert state.active_topic_id == tid
        assert state.selected_pid is None

    def test_assign_with_no_selection_returns_false(self, state):
        _pid, tid = self._setup(state)
        assert state.selected_pid is None
        assert state.assign(tid) is False
        assert state.snapshot()["topics"][0]["status"] == "open"

    def test_assign_to_non_open_topic_returns_false(self, state):
        pid, tid = self._setup(state)
        state.select_participant(pid)
        assert state.assign(tid) is True  # now active
        # Select someone else and try to assign the same (now active) topic.
        state.add_manual("Bob")
        state.select_participant(_pid_of(state, "Bob"))
        assert state.assign(tid) is False

    def test_assign_unknown_topic_returns_false(self, state):
        pid, _tid = self._setup(state)
        state.select_participant(pid)
        assert state.assign("nope") is False

    def test_assign_to_departed_participant_returns_false(self, state):
        # Rolled, then left the call before a topic was handed over.
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        tid = state.add_topic("A topic")
        state.select_participant(_pid_of(state, "Bob"))
        # Bob drops off the panel -> present=False (still in the dict).
        state.sync_participants([{"name": "Alice", "is_host": False}])
        assert state.assign(tid) is False
        assert state.selected_pid is None
        assert state.snapshot()["topics"][0]["status"] == "open"


class TestMarkDone:
    def test_mark_done_sets_status_and_answered(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        assert state.mark_done(tid) is True
        t = state.snapshot()["topics"][0]
        assert t["status"] == "done"
        assert _by_name(state, "Alice")["answered"] is True
        # Was the active topic, so active id clears.
        assert state.active_topic_id is None

    def test_mark_done_unknown_returns_false(self, state):
        assert state.mark_done("nope") is False

    def test_mark_done_leaves_other_active_topic_alone(self, state):
        # Done-ing a non-active topic must not clear an unrelated active id.
        state.add_manual("Alice")
        state.add_manual("Bob")
        t1 = state.add_topic("T1")
        t2 = state.add_topic("T2")
        # Make t1 active via Alice.
        state.select_participant(_pid_of(state, "Alice"))
        state.assign(t1)
        assert state.active_topic_id == t1
        # t2 is just open; mark it done directly.
        assert state.mark_done(t2) is True
        assert state.active_topic_id == t1


class TestReopenTopic:
    def test_reopen_resets_topic_and_assignee(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        state.mark_done(tid)
        assert _by_name(state, "Alice")["answered"] is True
        assert state.reopen_topic(tid) is True
        t = state.snapshot()["topics"][0]
        assert t["status"] == "open"
        assert t["assignee"] is None
        assert _by_name(state, "Alice")["answered"] is False

    def test_reopen_active_topic_clears_active_id(self, state):
        state.add_manual("Alice")
        tid = state.add_topic("Topic")
        state.select_participant(_pid_of(state, "Alice"))
        state.assign(tid)
        assert state.active_topic_id == tid
        assert state.reopen_topic(tid) is True
        assert state.active_topic_id is None

    def test_reopen_unknown_returns_false(self, state):
        assert state.reopen_topic("nope") is False


class TestReset:
    def test_reset_keeps_topics_and_participants_but_clears_round(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        state.mark_done(tid)
        started_before = state.snapshot()["startedAt"]

        state.reset()
        snap = state.snapshot()
        # Roster and topics survive.
        assert _names(snap) == ["Alice"]
        assert len(snap["topics"]) == 1
        # Round state is wiped.
        t = snap["topics"][0]
        assert t["status"] == "open"
        assert t["assignee"] is None
        assert _by_name(state, "Alice")["answered"] is False
        assert snap["selected"] is None
        assert snap["activeTopicId"] is None
        assert snap["startedAt"] >= started_before


class TestRemoveParticipant:
    def test_remove_drops_from_dict_and_order(self, state):
        state.sync_participants(
            [
                {"name": "Alice", "is_host": False},
                {"name": "Bob", "is_host": False},
            ]
        )
        pid = _pid_of(state, "Alice")
        state.remove(pid)
        assert _names(state.snapshot()) == ["Bob"]
        with state.lock:
            assert pid not in state.participants
            assert pid not in state.order

    def test_remove_unknown_pid_is_safe(self, state):
        # Should not raise.
        state.remove("nope")

    def test_remove_clears_selection_if_selected(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        state.select_participant(pid)
        state.remove(pid)
        assert state.selected_pid is None

    def test_remove_frees_held_topic_and_clears_active(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        assert state.active_topic_id == tid
        state.remove(pid)
        t = state.snapshot()["topics"][0]
        assert t["assignee"] is None
        assert t["status"] == "open"
        assert state.active_topic_id is None

    def test_remove_keeps_completed_topic_done(self, state):
        # Tidying the roster must not resurrect a finished prompt.
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        state.mark_done(tid)
        state.remove(pid)
        assert state.snapshot()["topics"][0]["status"] == "done"


class TestDemo:
    def test_start_demo_sets_flag_and_seeds(self, state):
        state.start_demo()
        snap = state.snapshot()
        assert snap["demo"] is True
        assert len(snap["participants"]) == len(DEMO_PARTICIPANTS)
        assert len(snap["topics"]) == len(DEMO_TOPICS)

    def test_start_demo_has_one_host_pinned_first(self, state):
        state.start_demo()
        snap = state.snapshot()
        hosts = [p for p in snap["participants"] if p["is_host"]]
        assert len(hosts) == 1
        assert snap["participants"][0]["is_host"] is True

    def test_start_demo_leaves_a_rollable_pool(self, state):
        state.start_demo()
        # Every roll lands on a present, unanswered, non-host sample speaker.
        random.seed(0)
        for _ in range(30):
            pid = state.pick_random()
            assert pid is not None
            p = state.participants[pid]
            assert p["is_host"] is False
            assert p["present"] is True
            assert p["answered"] is False
            state.cancel_pick()

    def test_start_demo_replaces_existing_state(self, state):
        state.add_manual("Real Person")
        state.add_topic("Real topic")
        state.start_demo()
        names = _names(state.snapshot())
        assert "Real Person" not in names
        headlines = [t["headline"] for t in state.snapshot()["topics"]]
        assert "Real topic" not in headlines

    def test_stop_demo_clears_everything(self, state):
        state.start_demo()
        # Run a little of the flow so there's round state to clear.
        pid = state.pick_random()
        tid = state.snapshot()["topics"][0]["id"]
        state.assign(tid)
        state.stop_demo()
        snap = state.snapshot()
        assert snap["demo"] is False
        assert snap["participants"] == []
        assert snap["topics"] == []
        assert snap["selected"] is None
        assert snap["activeTopicId"] is None
        assert pid is not None  # sanity: a pick really happened before the stop

    def test_sync_participants_ignored_during_demo(self, state):
        state.start_demo()
        before = _names(state.snapshot())
        # A live Zoom read must not touch the demo roster.
        assert state.sync_participants([{"name": "Intruder", "is_host": True}]) is False
        assert _names(state.snapshot()) == before

    def test_sync_resumes_after_stop_demo(self, state):
        state.start_demo()
        state.stop_demo()
        assert state.sync_participants([{"name": "Alice", "is_host": False}]) is True
        assert _names(state.snapshot()) == ["Alice"]


class TestSnapshot:
    def test_has_expected_keys(self, state):
        snap = state.snapshot()
        assert set(snap.keys()) == {
            "startedAt",
            "participants",
            "topics",
            "selected",
            "activeTopicId",
            "demo",
        }

    def test_assignee_resolves_to_id_name_or_null(self, state):
        state.add_manual("Alice")
        tid = state.add_topic("Topic")
        # Unassigned -> null.
        assert state.snapshot()["topics"][0]["assignee"] is None
        # Assigned -> {id, name}.
        pid = _pid_of(state, "Alice")
        state.select_participant(pid)
        state.assign(tid)
        assignee = state.snapshot()["topics"][0]["assignee"]
        assert assignee == {"id": pid, "name": "Alice"}

    def test_selected_resolves_to_id_name(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        state.select_participant(pid)
        assert state.snapshot()["selected"] == {"id": pid, "name": "Alice"}

    def test_snapshot_is_a_deep_copy(self, state):
        state.add_manual("Alice")
        state.add_topic("Topic")
        snap1 = state.snapshot()
        snap1["participants"][0]["name"] = "Mutated"
        snap1["topics"][0]["headline"] = "Mutated"
        snap2 = state.snapshot()
        assert snap2["participants"][0]["name"] == "Alice"
        assert snap2["topics"][0]["headline"] == "Topic"
