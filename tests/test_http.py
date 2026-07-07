"""End-to-end tests for the HTTP handler — spin up the real server on an
ephemeral port and hit it with urllib (no extra deps)."""

import http.client
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
    whole meeting via the same helper the demo teardown uses.
    """
    with STATE.lock:
        STATE._wipe()
        STATE.demo = False
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

    def test_serves_asset_with_query_string(self, server):
        # A cache-buster query must still resolve to the static asset.
        code, content_type, _ = _get_headers(server + "/app.js?v=1")
        assert code == 200
        assert "text/javascript" in content_type

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
        # No reselect in the body, so the round's selection stays cleared.
        assert STATE.snapshot()["selected"] is None

    def test_reopen_reselect_restores_the_selection(self, server):
        # The focus "Back" button sends {"reselect": true}: the topic reopens and
        # the same person is put back up, ready to pick a different topic.
        pid = _add_participant(server, "Alice")
        tid = _add_topic(server, "Topic")
        _post(server + "/api/select", {"pid": pid})
        _post(f"{server}/api/topic/{tid}/assign")
        code, body = _post(f"{server}/api/topic/{tid}/reopen", {"reselect": True})
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["topics"][0]["status"] == "open"
        assert STATE.snapshot()["selected"]["id"] == pid

    def test_unknown_action_returns_404(self, server):
        tid = _add_topic(server, "Topic")
        code, _ = _post(f"{server}/api/topic/{tid}/dance")
        assert code == 404


class TestPostRouting:
    def test_post_with_query_string_still_routes(self, server):
        # POST routes on the path component only (same as GET), so a query
        # string like a cache-buster can't turn a valid action into a 404.
        _add_participant(server, "Alice")
        code, body = _post(server + "/api/pick?ts=123")
        assert code == 200
        assert body["ok"] is True

    def test_unread_body_does_not_desync_keep_alive(self, server):
        # /api/reset ignores its body; the handler must still drain it, or the
        # next request on this persistent connection is parsed from the
        # leftover bytes and comes back garbage.
        host = server.removeprefix("http://")
        conn = http.client.HTTPConnection(host, timeout=5)
        try:
            padding = json.dumps({"padding": "x" * 256}).encode()
            for _ in range(2):
                conn.request(
                    "POST",
                    "/api/reset",
                    body=padding,
                    headers={"Content-Type": "application/json"},
                )
                resp = conn.getresponse()
                assert resp.status == 200
                assert json.loads(resp.read()) == {"ok": True}
        finally:
            conn.close()

    def test_malformed_content_length_closes_the_connection(self, server):
        # With an unparseable Content-Length the body length is unknowable, so
        # the handler can't drain it — it must close the connection instead of
        # letting the stray bytes desync the next keep-alive request.
        host = server.removeprefix("http://")
        conn = http.client.HTTPConnection(host, timeout=5)
        try:
            conn.putrequest("POST", "/api/reset")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", "not-a-number")
            conn.endheaders(message_body=b"{}")
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()
            # The server hung up; reusing the socket fails instead of parsing
            # the leftover body bytes as a new request.
            with pytest.raises((http.client.RemoteDisconnected, ConnectionError)):
                conn.request("POST", "/api/reset", body=b"{}")
                conn.getresponse()
        finally:
            conn.close()


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


class TestDemo:
    def test_start_seeds_and_sets_flag(self, server):
        code, body = _post(server + "/api/demo/start")
        assert code == 200
        assert body == {"ok": True}
        snap = STATE.snapshot()
        assert snap["demo"] is True
        assert len(snap["participants"]) > 0
        assert len(snap["topics"]) > 0

    def test_stop_returns_clean_slate(self, server):
        _post(server + "/api/demo/start")
        code, body = _post(server + "/api/demo/stop")
        assert code == 200
        assert body == {"ok": True}
        snap = STATE.snapshot()
        assert snap["demo"] is False
        assert snap["participants"] == []
        assert snap["topics"] == []


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

    def test_exclude_toggles_the_flag(self, server):
        pid = _add_participant(server, "Alice")
        code, body = _post(
            f"{server}/api/participant/{pid}/exclude", {"excluded": True}
        )
        assert code == 200
        assert body == {"ok": True}
        assert STATE.snapshot()["participants"][0]["excluded"] is True
        code, _ = _post(f"{server}/api/participant/{pid}/exclude", {"excluded": False})
        assert code == 200
        assert STATE.snapshot()["participants"][0]["excluded"] is False

    def test_exclude_unknown_pid_returns_404(self, server):
        code, body = _post(f"{server}/api/participant/nope/exclude", {"excluded": True})
        assert code == 404
        assert body == {"ok": False}

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
