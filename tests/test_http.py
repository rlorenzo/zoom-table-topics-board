"""End-to-end tests for the HTTP handler — spin up the real server on an
ephemeral port and hit it with urllib (no extra deps)."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import board
from board import STATE, Handler


@pytest.fixture
def server():
    """Run the real handler on 127.0.0.1:<random> for the test, then tear down.

    `STATE` is a module-global shared across tests, and `reset()` does NOT
    clear topics or participants (it only resets the round). So we wipe the
    whole roster + topic set by hand under the lock for a clean slate.
    """
    with STATE.lock:
        STATE.participants.clear()
        STATE.order.clear()
        STATE.topics.clear()
        STATE.topic_order.clear()
        STATE.selected_pid = None
        STATE.active_topic_id = None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


def _req(method, url, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _post(url, body=None):
    code, raw = _req("POST", url, body or {})
    return code, (json.loads(raw) if raw else None)


def _get(url):
    code, raw = _req("GET", url)
    return code, raw


def _get_headers(url):
    """GET returning (status, Content-Type, body) for header assertions."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def _add_participant(server, name):
    """Add a manual participant and return its id."""
    _post(server + "/api/participant", {"name": name})
    for p in STATE.snapshot()["participants"]:
        if p["name"] == name:
            return p["id"]
    raise KeyError(name)


def _add_topic(server, headline):
    code, body = _post(server + "/api/topic", {"headline": headline})
    assert code == 200
    return body["id"]


class TestGetRoot:
    def test_serves_index_html(self, server):
        code, raw = _get(server + "/")
        assert code == 200
        assert b"<html" in raw.lower() or b"<!doctype" in raw.lower()

    def test_index_path_alias(self, server):
        code, _ = _get(server + "/index.html")
        assert code == 200

    def test_unknown_get_returns_404(self, server):
        code, _ = _get(server + "/api/bogus")
        assert code == 404

    def test_missing_index_html(self, server, monkeypatch, tmp_path):
        # Point INDEX_HTML to a nonexistent file and verify the 500 response.
        monkeypatch.setattr(board, "INDEX_HTML", str(tmp_path / "nope.html"))
        code, raw = _get(server + "/")
        assert code == 500
        assert b"index.html missing" in raw


class TestStaticAssets:
    @pytest.mark.parametrize(
        "path, ctype, needle",
        [
            ("/app.js", "text/javascript", b'from "./lib.js"'),
            ("/lib.js", "text/javascript", b"export function escapeHtml"),
            ("/styles.css", "text/css", b"{"),
        ],
    )
    def test_serves_web_assets(self, server, path, ctype, needle):
        code, content_type, raw = _get_headers(server + path)
        assert code == 200
        assert ctype in content_type
        assert needle in raw

    def test_missing_asset_returns_404(self, server, monkeypatch, tmp_path):
        # A configured asset whose file is missing 404s (not 500, unlike index).
        monkeypatch.setattr(
            board,
            "STATIC_FILES",
            {"/app.js": (str(tmp_path / "nope.js"), "text/javascript; charset=utf-8")},
        )
        code, _, raw = _get_headers(server + "/app.js")
        assert code == 404
        assert b"not found" in raw


class TestPostAddParticipant:
    def test_adds_manual_participant(self, server):
        code, body = _post(server + "/api/participant", {"name": "Alice"})
        assert code == 200
        assert body == {"ok": True}
        names = [p["name"] for p in STATE.snapshot()["participants"]]
        assert "Alice" in names

    def test_empty_name_returns_400(self, server):
        code, body = _post(server + "/api/participant", {"name": "   "})
        assert code == 400
        assert body == {"error": "name required"}

    def test_missing_name_returns_400(self, server):
        code, _ = _post(server + "/api/participant", {})
        assert code == 400


class TestPostTopic:
    def test_adds_topic_and_returns_id(self, server):
        code, body = _post(server + "/api/topic", {"headline": "What is courage?"})
        assert code == 200
        assert body["ok"] is True
        assert "id" in body
        headlines = [t["headline"] for t in STATE.snapshot()["topics"]]
        assert "What is courage?" in headlines

    def test_blank_headline_returns_400(self, server):
        code, body = _post(server + "/api/topic", {"headline": "   "})
        assert code == 400
        assert body == {"error": "headline required"}


class TestPostTopics:
    def test_bulk_append_returns_added(self, server):
        code, body = _post(
            server + "/api/topics",
            {"topics": [{"headline": "One"}, {"headline": "Two"}]},
        )
        assert code == 200
        assert body == {"ok": True, "added": 2}

    def test_replace_clears_existing(self, server):
        _add_topic(server, "Old")
        code, body = _post(
            server + "/api/topics",
            {"topics": [{"headline": "New"}], "replace": True},
        )
        assert code == 200
        assert body == {"ok": True, "added": 1}
        headlines = [t["headline"] for t in STATE.snapshot()["topics"]]
        assert headlines == ["New"]

    def test_non_list_topics_returns_400(self, server):
        code, body = _post(server + "/api/topics", {"topics": "nope"})
        assert code == 400
        assert "list" in body["error"]


class TestTopicActions:
    def test_edit_success_and_unknown(self, server):
        tid = _add_topic(server, "Original")
        code, body = _post(
            f"{server}/api/topic/{tid}/edit",
            {"headline": "Updated", "details": "d"},
        )
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["topics"][0]["headline"] == "Updated"
        # Unknown topic id -> 400 {ok: false}.
        code, body = _post(f"{server}/api/topic/nope/edit", {"headline": "x"})
        assert code == 400
        assert body == {"ok": False}

    def test_remove_success_and_unknown(self, server):
        tid = _add_topic(server, "Doomed")
        code, body = _post(f"{server}/api/topic/{tid}/remove")
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["topics"] == []
        code, body = _post(f"{server}/api/topic/nope/remove")
        assert code == 400
        assert body == {"ok": False}

    def test_assign_success_and_no_selection_failure(self, server):
        pid = _add_participant(server, "Alice")
        tid = _add_topic(server, "Topic")
        # No selection yet -> assign fails.
        code, body = _post(f"{server}/api/topic/{tid}/assign")
        assert code == 400
        assert body == {"ok": False}
        # Select Alice, then assign succeeds.
        _post(server + "/api/select", {"pid": pid})
        code, body = _post(f"{server}/api/topic/{tid}/assign")
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["topics"][0]["status"] == "active"

    def test_done_success_and_unknown(self, server):
        pid = _add_participant(server, "Alice")
        tid = _add_topic(server, "Topic")
        _post(server + "/api/select", {"pid": pid})
        _post(f"{server}/api/topic/{tid}/assign")
        code, body = _post(f"{server}/api/topic/{tid}/done")
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["topics"][0]["status"] == "done"
        # Unknown id -> 400.
        code, body = _post(f"{server}/api/topic/nope/done")
        assert code == 400
        assert body == {"ok": False}

    def test_reopen_success(self, server):
        pid = _add_participant(server, "Alice")
        tid = _add_topic(server, "Topic")
        _post(server + "/api/select", {"pid": pid})
        _post(f"{server}/api/topic/{tid}/assign")
        _post(f"{server}/api/topic/{tid}/done")
        code, body = _post(f"{server}/api/topic/{tid}/reopen")
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["topics"][0]["status"] == "open"

    def test_unknown_action_returns_404(self, server):
        tid = _add_topic(server, "Topic")
        code, _ = _post(f"{server}/api/topic/{tid}/dance")
        assert code == 404


class TestSelection:
    def test_pick_returns_selected(self, server):
        pid = _add_participant(server, "Alice")
        code, body = _post(server + "/api/pick")
        assert code == 200
        assert body == {"ok": True, "selected": pid}

    def test_pick_with_nobody_eligible(self, server):
        code, body = _post(server + "/api/pick")
        assert code == 200
        assert body == {"ok": False, "selected": None}

    def test_select_success(self, server):
        pid = _add_participant(server, "Alice")
        code, body = _post(server + "/api/select", {"pid": pid})
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["selected"]["id"] == pid

    def test_select_unknown_pid_returns_404(self, server):
        code, body = _post(server + "/api/select", {"pid": "nope"})
        assert code == 404
        assert body == {"ok": False}

    def test_pick_cancel(self, server):
        pid = _add_participant(server, "Alice")
        _post(server + "/api/select", {"pid": pid})
        code, body = _post(server + "/api/pick/cancel")
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["selected"] is None


class TestReset:
    def test_reset(self, server):
        _add_topic(server, "Topic")
        _add_participant(server, "Alice")
        code, body = _post(server + "/api/reset")
        assert code == 200
        assert body == {"ok": True}
        # Reset keeps roster + topics but clears the round.
        snap = STATE.snapshot()
        assert len(snap["participants"]) == 1
        assert len(snap["topics"]) == 1
        assert snap["selected"] is None
        assert snap["activeTopicId"] is None


class TestParticipantRoutes:
    def test_set_host_promotes_to_first(self, server):
        _add_participant(server, "Alice")
        bob_pid = _add_participant(server, "Bob")
        code, _ = _post(f"{server}/api/participant/{bob_pid}/host", {"host": True})
        assert code == 200
        names = [p["name"] for p in STATE.snapshot()["participants"]]
        assert names[0] == "Bob"

    def test_remove(self, server):
        pid = _add_participant(server, "Alice")
        code, body = _post(f"{server}/api/participant/{pid}/remove")
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["participants"] == []

    def test_unknown_action_returns_404(self, server):
        pid = _add_participant(server, "Alice")
        code, _ = _post(f"{server}/api/participant/{pid}/dance")
        assert code == 404


class TestMalformedRequests:
    def test_malformed_json_falls_back_to_empty_body(self, server):
        # The handler swallows JSON errors and treats the body as {}.
        # On /api/topic, an empty body means no headline -> 400.
        req = urllib.request.Request(
            server + "/api/topic",
            data=b"not json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
                code, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        assert code == 400
        assert b"headline required" in raw


class TestOriginGuard:
    def test_cross_origin_post_is_rejected(self, server):
        req = urllib.request.Request(
            server + "/api/reset",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "http://evil.example",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 403

    def test_same_origin_post_is_allowed(self, server):
        host = server.removeprefix("http://")  # "127.0.0.1:<port>"
        req = urllib.request.Request(
            server + "/api/reset",
            data=b"{}",
            headers={"Content-Type": "application/json", "Origin": "http://" + host},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            assert resp.status == 200

    def test_post_without_origin_is_allowed(self, server):
        # Non-browser clients (curl, these tests) send no Origin header.
        code, body = _post(server + "/api/reset")
        assert code == 200
        assert body == {"ok": True}


class TestSSE:
    def test_events_endpoint_sends_initial_snapshot(self, server):
        _add_participant(server, "Alice")
        # Open the SSE stream and read just the initial frame, then bail.
        with urllib.request.urlopen(server + "/events", timeout=5) as resp:  # nosec B310
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "text/event-stream"
            # The handler writes the initial snapshot immediately.
            line = resp.readline()
            assert line.startswith(b"data: ")
            payload = json.loads(line[len(b"data: ") :].strip())
            assert "topics" in payload
            assert "selected" in payload
            assert "activeTopicId" in payload
            names = [p["name"] for p in payload["participants"]]
            assert "Alice" in names
