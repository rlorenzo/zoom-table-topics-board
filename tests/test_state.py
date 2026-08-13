"""Tests for the State class in board.py."""

import random

import pytest

import board
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
        # Manual entries have source "manual", so the panel-tracking pass
        # (which only manages source "auto") leaves them alone.
        state.add_manual("Carol")
        state.sync_participants([{"name": "Alice", "is_host": False}])
        carol = _by_name(state, "Carol")
        assert carol["present"] is True
        assert carol["leftTime"] is None

    def test_source_records_where_each_entry_came_from(self, state):
        state.add_manual("Manny")
        state.sync_participants([{"name": "Autumn", "is_host": False}])
        assert _by_name(state, "Manny")["source"] == "manual"
        assert _by_name(state, "Autumn")["source"] == "auto"
        state.start_demo()
        assert all(p["source"] == "demo" for p in state.snapshot()["participants"])

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
        # sync_participants([]) clears the AX roster (everyone marked left). The
        # poller no longer calls this on an empty read, but the State contract
        # must stay correct for the genuine "everyone gone" case.
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

    def test_eligible_get_chosen_including_the_host(self, state):
        self._seed_pool(state)
        chosen = {state.pick_random() for _ in range(50)}
        # Every chosen id resolves to a present, unanswered participant — the
        # host included, since the host is now a full participant.
        for pid in chosen:
            p = state.participants[pid]
            assert p["present"] is True
            assert p["answered"] is False

    def test_host_can_be_rolled(self, state):
        self._seed_pool(state)
        host_pid = _pid_of(state, "Host")
        # Answer everyone except the host, leaving the host the only eligible pick.
        for name in ("Alice", "Bob", "Carol"):
            _by_name(state, name)["answered"] = True
        for _ in range(20):
            assert state.pick_random() == host_pid

    def test_answered_are_excluded(self, state):
        self._seed_pool(state)
        # Mark everyone but Alice answered (the host too, now that they're rolled).
        for n in ("Host", "Bob", "Carol"):
            _by_name(state, n)["answered"] = True
        random.seed(0)
        for _ in range(20):
            assert state.pick_random() == _pid_of(state, "Alice")

    def test_not_present_are_excluded(self, state):
        self._seed_pool(state)
        # Only Alice stays in the panel; the host, Bob, and Carol leave.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        random.seed(0)
        for _ in range(20):
            assert state.pick_random() == _pid_of(state, "Alice")

    def test_empty_pool_returns_none_and_clears_selection(self, state):
        # One participant, already answered, so nobody is eligible.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        _by_name(state, "Alice")["answered"] = True
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
        state.sync_participants([{"name": "Solo", "is_host": False}])
        solo = _pid_of(state, "Solo")
        assert state.pick_random(exclude_pid=solo) == solo
        assert state.selected_pid == solo

    def test_pick_sets_selected_pid(self, state):
        self._seed_pool(state)
        random.seed(42)
        chosen = state.pick_random()
        assert state.selected_pid == chosen

    def test_active_topic_holder_is_not_rolled(self, state):
        state.add_manual("Alice")
        state.add_manual("Bob")
        tid = state.add_topic("T1")
        alice = _pid_of(state, "Alice")
        state.select_participant(alice)
        state.assign(tid)
        # Alice is mid-answer on an active topic; only Bob can be rolled.
        for _ in range(20):
            assert state.pick_random() == _pid_of(state, "Bob")


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

    def test_active_topic_holder_cannot_be_selected_again(self, state):
        # Someone mid-answer already has the mic: selecting them again would
        # let a second topic be assigned to them simultaneously.
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("T1")
        state.select_participant(pid)
        state.assign(tid)
        assert state.select_participant(pid) is False
        assert state.selected_pid is None


class TestCancelPick:
    def test_clears_selected_pid(self, state):
        state.add_manual("Alice")
        state.select_participant(_pid_of(state, "Alice"))
        assert state.selected_pid is not None
        state.cancel_pick()
        assert state.selected_pid is None


class TestSetExcluded:
    def test_added_participant_defaults_to_not_excluded(self, state):
        state.add_manual("Alice")
        assert _by_name(state, "Alice")["excluded"] is False

    def test_toggles_the_flag_on_and_off(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        assert state.set_excluded(pid, True) is True
        assert _by_name(state, "Alice")["excluded"] is True
        assert state.set_excluded(pid, False) is True
        assert _by_name(state, "Alice")["excluded"] is False

    def test_unknown_pid_returns_false(self, state):
        assert state.set_excluded("nope", True) is False

    def test_excluded_people_are_not_rolled(self, state):
        state.add_manual("Alice")
        state.add_manual("Bob")
        state.set_excluded(_pid_of(state, "Bob"), True)
        alice = _pid_of(state, "Alice")
        for _ in range(20):
            assert state.pick_random() == alice

    def test_excluded_person_cannot_be_selected(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        state.set_excluded(pid, True)
        assert state.select_participant(pid) is False

    def test_excluding_selected_person_drops_the_selection(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        state.select_participant(pid)
        assert state.selected_pid == pid
        state.set_excluded(pid, True)
        assert state.selected_pid is None

    def test_persists_across_reset(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        state.set_excluded(pid, True)
        state.reset()
        assert _by_name(state, "Alice")["excluded"] is True


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

    def test_reopen_reselect_returns_to_topic_list(self, state):
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        assert state.reopen_topic(tid, reselect=True) is True
        assert state.active_topic_id is None
        assert state.selected_pid == pid

    def test_reopen_reselect_skips_an_excluded_assignee(self, state):
        # If the assignee opted out after being handed the topic, the focus
        # "Back" button must not re-select them — set_excluded promises an
        # excluded person can never end up selected.
        state.add_manual("Alice")
        pid = _pid_of(state, "Alice")
        tid = state.add_topic("Topic")
        state.select_participant(pid)
        state.assign(tid)
        state.set_excluded(pid, True)
        assert state.reopen_topic(tid, reselect=True) is True
        assert state.selected_pid is None

    def test_reopen_without_reselect_leaves_selection_cleared(self, state):
        state.add_manual("Alice")
        tid = state.add_topic("Topic")
        state.select_participant(_pid_of(state, "Alice"))
        state.assign(tid)
        assert state.reopen_topic(tid) is True
        assert state.selected_pid is None


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
        # Every roll lands on a present, unanswered sample speaker (the host
        # included — they're a full participant now).
        random.seed(0)
        for _ in range(30):
            pid = state.pick_random()
            assert pid is not None
            p = state.participants[pid]
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


class TestParticipantIdentity:
    """Participant ids must not be derived from the display name.

    Zoom's panel is only a list of display names, so hashing the name made the
    name the identity. On a board that picks a speaker at random the two
    failure modes are both user-visible: a duplicate name means one of those
    people can never be drawn, and a rename means someone who already spoke
    loses their "answered" flag and can be drawn again.
    """

    def test_rename_keeps_the_same_row_and_its_answered_flag(self, state):
        state.sync_participants([{"name": "Rex Lorenzo", "is_host": True}])
        pid = _pid_of(state, "Rex Lorenzo")
        state.participants[pid]["answered"] = True

        state.sync_participants([{"name": "Rex L.", "is_host": True}])

        assert _names(state.snapshot()) == ["Rex L."]
        renamed = _by_name(state, "Rex L.")
        assert renamed["id"] == pid
        assert renamed["answered"] is True
        assert renamed["present"] is True

    def test_rename_leaves_the_other_participants_untouched(self, state):
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bob", "is_host": False}]
        )
        alice, bob = _pid_of(state, "Alice"), _pid_of(state, "Bob")

        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bobby", "is_host": False}]
        )

        assert _pid_of(state, "Alice") == alice  # matched by name, not paired up
        assert _pid_of(state, "Bobby") == bob
        assert len(state.participants) == 2

    def test_duplicate_display_names_stay_on_separate_rows(self, state):
        people = [
            {"name": "John Smith", "is_host": False},
            {"name": "John Smith", "is_host": False},
        ]
        state.sync_participants(people)
        assert _names(state.snapshot()) == ["John Smith", "John Smith"]
        ids = [p["id"] for p in state.participants.values()]
        assert len(set(ids)) == 2

        # Both rows must survive the next poll rather than one being re-minted:
        # each name is matched against the pool one-for-one and consumed.
        state.sync_participants(people)
        assert [p["id"] for p in state.participants.values()] == ids

    def test_ambiguous_swap_is_a_leave_plus_join_not_a_rename(self, state):
        # Two out and two in inside one poll leaves more than one possible
        # pairing. Guessing wrong would carry someone's answered flag onto the
        # wrong person, so we decline to guess.
        state.sync_participants(
            [{"name": "A", "is_host": False}, {"name": "B", "is_host": False}]
        )
        state.sync_participants(
            [{"name": "C", "is_host": False}, {"name": "D", "is_host": False}]
        )
        assert _by_name(state, "A")["present"] is False
        assert _by_name(state, "B")["present"] is False
        assert _by_name(state, "C")["present"] is True
        assert _by_name(state, "D")["present"] is True

    def test_one_for_one_swap_is_read_as_a_rename_by_design(self, state):
        """Pins the known, accepted cost of the one-for-one rule.

        A departure and an unrelated arrival landing in the same poll is
        indistinguishable from a rename: the panel yields display names only,
        so both events look like "this name went, that name came". We take the
        rename reading on purpose — a rename is atomic and *always* lands in
        one poll, whereas this conflation needs two unrelated events inside
        the same --interval window (5s by default).

        The cost when we guess wrong is recorded here rather than left to the
        docstring: the newcomer inherits the departed row. It is bounded and
        host-correctable (reopen_topic clears answered, set_excluded toggles
        the opt-out, remove() drops the row and the next poll mints a fresh
        id). Flip these assertions only alongside a deliberate decision to
        change the rule in State._apply_rename.
        """
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bob", "is_host": False}]
        )
        bob = _pid_of(state, "Bob")
        state.participants[bob]["answered"] = True
        state.participants[bob]["excluded"] = True
        state.selected_pid = bob

        # Bob leaves and an unrelated Carol joins, both within one poll.
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Carol", "is_host": False}]
        )

        carol = _by_name(state, "Carol")
        assert carol["id"] == bob  # Bob's row, relabelled
        assert carol["answered"] is True
        assert carol["excluded"] is True
        assert state.selected_pid == bob
        # No ghost row is left behind: the roster still holds exactly two rows.
        assert _names(state.snapshot()) == ["Alice", "Carol"]

    def test_rename_does_not_consume_a_manual_row(self, state):
        # Manual entries are never panel-tracked, so they must not be offered
        # up as the "vanished" half of a rename pairing.
        state.add_manual("Typed Person")
        state.sync_participants([{"name": "Zoom Person", "is_host": False}])
        state.sync_participants([{"name": "Zoom Person Renamed", "is_host": False}])

        typed = _by_name(state, "Typed Person")
        assert typed["source"] == "manual"
        assert typed["present"] is True
        assert _by_name(state, "Zoom Person Renamed")["source"] == "auto"

    def test_a_departure_alone_is_not_read_as_a_rename(self, state):
        # One person vanishes and nobody new appears: no pairing to make.
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bob", "is_host": False}]
        )
        state.sync_participants([{"name": "Alice", "is_host": False}])
        assert _by_name(state, "Bob")["present"] is False
        assert _by_name(state, "Alice")["present"] is True

    def test_arrival_after_a_recorded_departure_is_a_join(self, state):
        # Only *present* people are rename candidates. Bob's departure was
        # already banked a poll earlier, so Carol is a newcomer — pairing them
        # would hand Bob's row to a stranger who merely arrived next.
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bob", "is_host": False}]
        )
        bob = _pid_of(state, "Bob")
        state.sync_participants([{"name": "Alice", "is_host": False}])
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Carol", "is_host": False}]
        )
        assert _pid_of(state, "Carol") != bob
        assert _by_name(state, "Bob")["present"] is False

    def test_rejoining_under_the_same_name_reuses_the_row(self, state):
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bob", "is_host": False}]
        )
        pid = _pid_of(state, "Bob")
        state.sync_participants([{"name": "Alice", "is_host": False}])
        state.sync_participants(
            [{"name": "Alice", "is_host": False}, {"name": "Bob", "is_host": False}]
        )
        assert _pid_of(state, "Bob") == pid

    def test_new_round_keeps_the_roster_and_its_ids(self, state):
        # reset() is "new round": same people, cleared flags. Their ids must
        # survive it, or every connected client's view would be invalidated.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        first = _pid_of(state, "Alice")
        state.reset()
        assert _pid_of(state, "Alice") == first

    def test_ids_are_never_reused_after_the_roster_is_wiped(self, state):
        state.sync_participants([{"name": "Alice", "is_host": False}])
        first = _pid_of(state, "Alice")
        state.start_demo()  # wipes the roster
        state.stop_demo()
        state.sync_participants([{"name": "Alice", "is_host": False}])
        # A stale client must never address a departed person's row.
        assert _pid_of(state, "Alice") != first

    def test_ids_are_never_reused_after_a_removal(self, state):
        state.sync_participants([{"name": "Alice", "is_host": False}])
        first = _pid_of(state, "Alice")
        state.remove(first)
        state.sync_participants([{"name": "Alice", "is_host": False}])
        assert _pid_of(state, "Alice") != first

    def test_manual_adds_of_the_same_name_get_distinct_ids(self, state):
        state.add_manual("Sam")
        state.add_manual("Sam")
        assert len(state.participants) == 2
        assert _names(state.snapshot()) == ["Sam", "Sam"]

    def test_id_prefix_records_where_the_row_came_from(self, state):
        state.add_manual("Manny")
        state.sync_participants([{"name": "Autumn", "is_host": False}])
        assert _pid_of(state, "Manny").startswith("m")
        assert _pid_of(state, "Autumn").startswith("a")


class TestSessionPersistence:
    """Crash recovery, scoped so it can't outlive the meeting it belongs to.

    PRODUCT.md keeps the roster and matching ephemeral across meetings; these
    tests pin the boundary that makes both true at once -- a clean exit and a
    stale file both leave nothing to restore, while a run that died mid-meeting
    can be picked back up.
    """

    @pytest.fixture
    def path(self, tmp_path):
        return str(tmp_path / ".board-session.json")

    @pytest.fixture
    def live(self, state, path):
        """A state that persists, mid-meeting: two people, one already gone."""
        state.session_path = path
        state.sync_participants(
            [{"name": "Alice", "is_host": True}, {"name": "Bob", "is_host": False}]
        )
        tid = state.add_topic("What is courage?", "some details")
        state.select_participant(_pid_of(state, "Alice"))
        state.assign(tid)
        state.mark_done(tid)
        state.persist(force=True)
        return state

    def test_persist_is_off_until_a_path_is_set(self, state, path):
        # The default must never touch the disk: library use and the test suite
        # both construct State freely.
        state.sync_participants([{"name": "Alice", "is_host": False}])
        state.persist(force=True)
        assert board.load_session(path) is None

    def test_round_trips_who_has_already_gone(self, live, path, state):
        restored = board.State()
        payload = board.load_session(path)
        assert payload is not None
        restored.restore_session(payload)

        assert _names(restored.snapshot()) == ["Alice", "Bob"]
        assert _by_name(restored, "Alice")["answered"] is True
        assert _by_name(restored, "Bob")["answered"] is False
        assert _by_name(restored, "Alice")["is_host"] is True

    def test_restored_topic_still_points_at_its_speaker(self, live, path):
        restored = board.State()
        restored.restore_session(board.load_session(path))
        snap = restored.snapshot()
        topic = _topic_by_headline(snap, "What is courage?")
        assert topic["status"] == "done"
        assert topic["assignee"]["name"] == "Alice"
        # Remapped onto the new id, not the saved one.
        assert topic["assignee"]["id"] == _pid_of(restored, "Alice")

    def test_restored_ids_do_not_collide_with_later_ones(self, live, path):
        # Ids are monotonic counters; adopting saved ids would let the counter
        # hand the same one out again later in the meeting.
        restored = board.State()
        restored.restore_session(board.load_session(path))
        existing = {p["id"] for p in restored.participants.values()}
        restored.add_manual("Carol")
        restored.sync_participants([{"name": "Dave", "is_host": False}])
        fresh = {p["id"] for p in restored.participants.values()} - existing
        assert len(fresh) == 2
        assert not (fresh & existing)

    def test_zoom_reads_reattach_to_restored_rows_by_name(self, live, path):
        # Ids are re-minted, so the next panel read must rejoin on name via the
        # normal pool matching -- otherwise everyone doubles up on resume.
        restored = board.State()
        restored.restore_session(board.load_session(path))
        restored.sync_participants(
            [{"name": "Alice", "is_host": True}, {"name": "Bob", "is_host": False}]
        )
        assert _names(restored.snapshot()) == ["Alice", "Bob"]
        assert _by_name(restored, "Alice")["answered"] is True

    def test_clean_exit_leaves_nothing_to_resume(self, live, path):
        board.clear_session(path)
        assert board.load_session(path) is None

    def test_a_stale_session_is_not_offered(self, live, path):
        # Older than the TTL means it belonged to an earlier meeting.
        assert board.load_session(path, ttl=0) is None
        assert board.load_session(path, ttl=3600) is not None

    @pytest.mark.parametrize(
        "content", ["", "not json at all", "[]", '{"schema": 999, "savedAt": 0}']
    )
    def test_unusable_files_are_declined_not_crashed(self, path, content):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        assert board.load_session(path) is None

    def test_demo_never_overwrites_a_real_session(self, live, path):
        before = board.load_session(path)
        live.start_demo()
        live.persist(force=True)
        after = board.load_session(path)
        assert [p["name"] for p in after["participants"]] == [
            p["name"] for p in before["participants"]
        ]

    def test_demo_participants_are_dropped_on_restore(self, state, path):
        state.session_path = path
        state.start_demo()
        # Force a demo payload onto disk the way a crash never would, to prove
        # restore itself refuses sample data rather than relying on the writer.
        payload = state.session_payload()
        restored = board.State()
        restored.restore_session(payload)
        assert restored.snapshot()["participants"] == []

    def test_orphaned_assignment_reopens_rather_than_dangling(self, path):
        payload = {
            "schema": board.SESSION_SCHEMA,
            "savedAt": __import__("time").time(),
            "participants": [],
            "topics": [
                {
                    "id": "t1",
                    "headline": "Orphan",
                    "details": "",
                    "status": "done",
                    "assignee": "a99",  # nobody survived the restore
                }
            ],
        }
        restored = board.State()
        restored.restore_session(payload)
        topic = _topic_by_headline(restored.snapshot(), "Orphan")
        assert topic["status"] == "open"
        assert topic["assignee"] is None

    def test_write_is_throttled_but_forceable(self, state, path):
        state.session_path = path
        state.sync_participants([{"name": "Alice", "is_host": False}])
        state.persist(force=True)
        first = board.load_session(path)
        state.add_manual("Bob")  # broadcast() -> persist(), inside the interval
        assert len(board.load_session(path)["participants"]) == len(
            first["participants"]
        )
        state.persist(force=True)
        assert len(board.load_session(path)["participants"]) == 2
