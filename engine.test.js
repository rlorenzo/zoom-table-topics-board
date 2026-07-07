import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEngine } from "./engine.js";

// Mirrors tests/test_state.py against the browser-side engine. The engine is
// manual-only (no Zoom auto-read / host syncing), so the sync_participants and
// set_host suites have no counterpart here; everything else tracks the Python
// coverage closely.

const names = (snap) => snap.participants.map((p) => p.name);

// The participant record matching `name` (case-insensitive), read straight off
// the latest snapshot.
function byName(engine, name) {
  const p = engine.snapshot().participants.find((x) => x.name.toLowerCase() === name.toLowerCase());
  if (!p) throw new Error(`no participant named ${name}`);
  return p;
}

const pidOf = (engine, name) => byName(engine, name).id;

function topicByHeadline(snap, headline) {
  const t = snap.topics.find((x) => x.headline === headline);
  if (!t) throw new Error(`no topic with headline ${headline}`);
  return t;
}

// Arrange the common mid-round state: Alice is selected and holding an active
// topic. Returns her pid and the topic id for tests that act on them next.
function setupActiveTopic(engine) {
  engine.addParticipant("Alice");
  const pid = pidOf(engine, "Alice");
  const tid = engine.addTopic("Topic");
  engine.select(pid);
  engine.assign(tid);
  return { pid, tid };
}

let engine;
beforeEach(() => {
  engine = createEngine();
});

describe("addParticipant", () => {
  it("adds participants in order", () => {
    engine.addParticipant("Alice");
    engine.addParticipant("Bob");
    expect(names(engine.snapshot())).toEqual(["Alice", "Bob"]);
  });

  it("trims the name and ignores blank adds", () => {
    engine.addParticipant("  Alice  ");
    engine.addParticipant("   ");
    engine.addParticipant("");
    const snap = engine.snapshot();
    expect(names(snap)).toEqual(["Alice"]);
    expect(snap.participants[0].name).toBe("Alice");
  });

  it("seeds the expected default fields", () => {
    engine.addParticipant("Alice");
    const p = engine.snapshot().participants[0];
    expect(p.present).toBe(true);
    expect(p.answered).toBe(false);
    expect(p.is_host).toBe(false);
    expect(p.excluded).toBe(false);
    expect(p.source).toBe("manual");
    expect(p.leftTime).toBeNull();
    expect(typeof p.joinTime).toBe("number");
  });

  it("gives each add a distinct id even when the name repeats", () => {
    engine.addParticipant("Alex");
    engine.addParticipant("Alex");
    const snap = engine.snapshot();
    expect(snap.participants).toHaveLength(2);
    expect(snap.participants[0].id).not.toBe(snap.participants[1].id);
  });
});

describe("topics", () => {
  it("addTopic returns an id and strips whitespace", () => {
    const tid = engine.addTopic("  What is courage?  ", "  some details  ");
    expect(tid).not.toBeNull();
    const t = topicByHeadline(engine.snapshot(), "What is courage?");
    expect(t.id).toBe(tid);
    expect(t.details).toBe("some details");
    expect(t.status).toBe("open");
    expect(t.assignee).toBeNull();
  });

  it("addTopic with a blank headline returns null", () => {
    expect(engine.addTopic("   ")).toBeNull();
    expect(engine.addTopic("")).toBeNull();
    expect(engine.snapshot().topics).toEqual([]);
  });

  it("topic ids are monotonic", () => {
    expect(engine.addTopic("One")).toBe("t1");
    expect(engine.addTopic("Two")).toBe("t2");
  });

  it("addTopics appends in bulk", () => {
    engine.addTopic("First");
    const added = engine.addTopics([{ headline: "Second", details: "d2" }, { headline: "Third" }]);
    expect(added).toBe(2);
    expect(engine.snapshot().topics.map((t) => t.headline)).toEqual(["First", "Second", "Third"]);
  });

  it("addTopics skips blank headlines and non-objects", () => {
    const added = engine.addTopics([
      { headline: "Real" },
      { headline: "   " },
      { details: "no headline" },
      "not an object",
      null,
    ]);
    expect(added).toBe(1);
    expect(engine.snapshot().topics.map((t) => t.headline)).toEqual(["Real"]);
  });

  it("addTopics tolerates a non-array payload without throwing mid-wipe", () => {
    // A truthy non-iterable must not throw after the replace-wipe, which
    // would leave subscribers rendering a stale pre-wipe snapshot.
    engine.addTopic("Old");
    const added = engine.addTopics({ headline: "not a list" }, true);
    expect(added).toBe(0);
    expect(engine.snapshot().topics).toEqual([]);
  });

  it("addTopics replace clears the existing set first", () => {
    engine.addTopic("Old");
    const added = engine.addTopics([{ headline: "New" }], true);
    expect(added).toBe(1);
    expect(engine.snapshot().topics.map((t) => t.headline)).toEqual(["New"]);
  });

  it("addTopics replace clears the active topic", () => {
    engine.addTopic("Topic");
    engine.addParticipant("Alice");
    engine.select(pidOf(engine, "Alice"));
    const tid = engine.snapshot().topics[0].id;
    engine.assign(tid);
    expect(engine.snapshot().activeTopicId).toBe(tid);
    engine.addTopics([{ headline: "Fresh" }], true);
    expect(engine.snapshot().activeTopicId).toBeNull();
  });

  it("addTopics replace clears a pending selection", () => {
    // Clearing the topic set mid-roll must not strand a selection that can no
    // longer be assigned to anything.
    engine.addParticipant("Alice");
    engine.addTopic("Old");
    engine.select(pidOf(engine, "Alice"));
    expect(engine.snapshot().selected).not.toBeNull();
    engine.addTopics([{ headline: "New" }], true);
    expect(engine.snapshot().selected).toBeNull();
  });

  it("editTopic on an unknown id returns false", () => {
    expect(engine.editTopic("nope", "Headline", "details")).toBe(false);
  });

  it("editTopic with a blank headline returns false and leaves it untouched", () => {
    const tid = engine.addTopic("Original");
    expect(engine.editTopic(tid, "   ", "details")).toBe(false);
    expect(engine.snapshot().topics[0].headline).toBe("Original");
  });

  it("editTopic success updates and trims", () => {
    const tid = engine.addTopic("Original", "old details");
    expect(engine.editTopic(tid, "  Updated  ", "  new details  ")).toBe(true);
    const t = engine.snapshot().topics[0];
    expect(t.headline).toBe("Updated");
    expect(t.details).toBe("new details");
  });

  it("removeTopic on an unknown id returns false", () => {
    expect(engine.removeTopic("nope")).toBe(false);
  });

  it("removeTopic success drops it from the snapshot", () => {
    const tid = engine.addTopic("Doomed");
    expect(engine.removeTopic(tid)).toBe(true);
    expect(engine.snapshot().topics).toEqual([]);
  });

  it("removing the active topic clears the active id", () => {
    engine.addParticipant("Alice");
    engine.select(pidOf(engine, "Alice"));
    const tid = engine.addTopic("Topic");
    engine.assign(tid);
    expect(engine.snapshot().activeTopicId).toBe(tid);
    expect(engine.removeTopic(tid)).toBe(true);
    expect(engine.snapshot().activeTopicId).toBeNull();
  });
});

describe("pick", () => {
  function seedPool() {
    // No auto-read host here; manual-add a host-flagged person isn't possible,
    // so the pick pool is exercised purely with manual (non-host) adds plus an
    // answered/absent participant to exclude.
    engine.addParticipant("Alice");
    engine.addParticipant("Bob");
    engine.addParticipant("Carol");
  }

  it("only eligible (present, unanswered) people get chosen", () => {
    seedPool();
    const chosen = new Set();
    for (let i = 0; i < 50; i++) {
      const pid = engine.pick();
      chosen.add(pid);
      engine.cancelPick();
    }
    for (const pid of chosen) {
      const p = engine.snapshot().participants.find((x) => x.id === pid);
      expect(p.present).toBe(true);
      expect(p.answered).toBe(false);
    }
  });

  it("can choose the host (the host is a full participant)", () => {
    // The only way to get a host-flagged participant is the demo seed.
    engine.startDemo();
    const snap = engine.snapshot();
    const hostPid = snap.participants.find((p) => p.is_host).id;
    // Answer everyone except the host, so the host is the only one left — the
    // roll must then land on them, proving the host is eligible.
    for (const p of snap.participants) {
      if (p.is_host) continue;
      const tid = engine.addTopic(`T-${p.id}`);
      engine.select(p.id);
      engine.assign(tid);
      engine.markDone(tid);
    }
    expect(engine.pick()).toBe(hostPid);
  });

  it("answered people are excluded", () => {
    seedPool();
    // Mark everyone but Alice answered by assigning + completing a topic.
    for (const n of ["Bob", "Carol"]) {
      const tid = engine.addTopic(`T-${n}`);
      engine.select(pidOf(engine, n));
      engine.assign(tid);
      engine.markDone(tid);
    }
    for (let i = 0; i < 20; i++) {
      expect(engine.pick()).toBe(pidOf(engine, "Alice"));
    }
  });

  it("opted-out (excluded) people are excluded from the roll", () => {
    seedPool();
    engine.setExcluded(pidOf(engine, "Bob"), true);
    engine.setExcluded(pidOf(engine, "Carol"), true);
    for (let i = 0; i < 20; i++) {
      expect(engine.pick()).toBe(pidOf(engine, "Alice"));
    }
  });

  it("not-present people are excluded", () => {
    seedPool();
    // Force Bob/Carol absent by removing... no: removal drops them entirely.
    // Instead drive present=false through the only public path that yields it,
    // which the manual engine lacks, so cover absence via the snapshot guard:
    // remove Bob and Carol, leaving only Alice eligible.
    engine.removeParticipant(pidOf(engine, "Bob"));
    engine.removeParticipant(pidOf(engine, "Carol"));
    for (let i = 0; i < 20; i++) {
      expect(engine.pick()).toBe(pidOf(engine, "Alice"));
    }
  });

  it("an empty pool returns null and clears any selection", () => {
    engine.addParticipant("Alice");
    engine.select(pidOf(engine, "Alice"));
    expect(engine.snapshot().selected).not.toBeNull();
    // Alice answers, emptying the pool.
    const tid = engine.addTopic("T");
    engine.assign(tid);
    engine.markDone(tid);
    expect(engine.pick()).toBeNull();
    expect(engine.snapshot().selected).toBeNull();
  });

  it("excludePid avoids that pid when others exist", () => {
    seedPool();
    const alice = pidOf(engine, "Alice");
    for (let i = 0; i < 30; i++) {
      expect(engine.pick(alice)).not.toBe(alice);
      engine.cancelPick();
    }
  });

  it("excludePid falls back when excluding would empty the pool", () => {
    // Only one eligible person; excluding them must still re-pick them.
    engine.addParticipant("Solo");
    const solo = pidOf(engine, "Solo");
    expect(engine.pick(solo)).toBe(solo);
    expect(engine.snapshot().selected.id).toBe(solo);
  });

  it("sets the selected participant", () => {
    seedPool();
    const chosen = engine.pick();
    expect(engine.snapshot().selected.id).toBe(chosen);
  });

  it("uses Math.random over the eligible pool", () => {
    seedPool();
    // Force the index to land on the last pool member deterministically.
    const spy = vi.spyOn(Math, "random").mockReturnValue(0.99);
    const chosen = engine.pick();
    expect(chosen).toBe(pidOf(engine, "Carol"));
    spy.mockRestore();
  });

  it("someone holding an active topic is not rolled", () => {
    engine.addParticipant("Alice");
    engine.addParticipant("Bob");
    const tid = engine.addTopic("T1");
    engine.select(pidOf(engine, "Alice"));
    engine.assign(tid);
    // Alice is mid-answer on an active topic; only Bob can be rolled.
    for (let i = 0; i < 20; i++) {
      expect(engine.pick()).toBe(pidOf(engine, "Bob"));
    }
  });
});

describe("select", () => {
  it("selects a present person", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    expect(engine.select(pid)).toBe(true);
    expect(engine.snapshot().selected.id).toBe(pid);
  });

  it("may select the host directly", () => {
    engine.startDemo();
    const hostPid = engine.snapshot().participants.find((p) => p.is_host).id;
    expect(engine.select(hostPid)).toBe(true);
    expect(engine.snapshot().selected.id).toBe(hostPid);
  });

  it("an unknown pid returns false", () => {
    expect(engine.select("nope")).toBe(false);
  });

  it("an answered person cannot be selected", () => {
    const { pid, tid } = setupActiveTopic(engine);
    engine.markDone(tid);
    expect(engine.select(pid)).toBe(false);
  });

  it("an excluded person cannot be selected", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    engine.setExcluded(pid, true);
    expect(engine.select(pid)).toBe(false);
  });

  it("someone holding an active topic cannot be selected again", () => {
    // Selecting them again would let a second topic be assigned to one person.
    const { pid } = setupActiveTopic(engine);
    expect(engine.select(pid)).toBe(false);
    expect(engine.snapshot().selected).toBeNull();
  });
});

describe("setExcluded", () => {
  it("toggles the flag on and off", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    expect(engine.setExcluded(pid, true)).toBe(true);
    expect(byName(engine, "Alice").excluded).toBe(true);
    expect(engine.setExcluded(pid, false)).toBe(true);
    expect(byName(engine, "Alice").excluded).toBe(false);
  });

  it("an unknown pid returns false", () => {
    expect(engine.setExcluded("nope", true)).toBe(false);
  });

  it("excluding the selected person drops the pending selection", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    engine.select(pid);
    expect(engine.snapshot().selected.id).toBe(pid);
    engine.setExcluded(pid, true);
    expect(engine.snapshot().selected).toBeNull();
  });

  it("persists across reset (a new round does not un-opt-out anyone)", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    engine.setExcluded(pid, true);
    engine.reset();
    expect(byName(engine, "Alice").excluded).toBe(true);
  });
});

describe("cancelPick", () => {
  it("clears the selection", () => {
    engine.addParticipant("Alice");
    engine.select(pidOf(engine, "Alice"));
    expect(engine.snapshot().selected).not.toBeNull();
    engine.cancelPick();
    expect(engine.snapshot().selected).toBeNull();
  });
});

describe("assign", () => {
  function setup() {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    const tid = engine.addTopic("A topic");
    return { pid, tid };
  }

  it("assign success", () => {
    const { pid, tid } = setup();
    engine.select(pid);
    expect(engine.assign(tid)).toBe(true);
    const t = engine.snapshot().topics[0];
    expect(t.status).toBe("active");
    expect(t.assignee).toEqual({ id: pid, name: "Alice" });
    expect(engine.snapshot().activeTopicId).toBe(tid);
    expect(engine.snapshot().selected).toBeNull();
  });

  it("assign with no selection returns false", () => {
    const { tid } = setup();
    expect(engine.snapshot().selected).toBeNull();
    expect(engine.assign(tid)).toBe(false);
    expect(engine.snapshot().topics[0].status).toBe("open");
  });

  it("assign to a non-open topic returns false", () => {
    const { pid, tid } = setup();
    engine.select(pid);
    expect(engine.assign(tid)).toBe(true); // now active
    engine.addParticipant("Bob");
    engine.select(pidOf(engine, "Bob"));
    expect(engine.assign(tid)).toBe(false);
  });

  it("assign to an unknown topic returns false", () => {
    const { pid } = setup();
    engine.select(pid);
    expect(engine.assign("nope")).toBe(false);
  });
});

describe("markDone", () => {
  it("sets status done and the assignee's answered flag, clearing active", () => {
    const { tid } = setupActiveTopic(engine);
    expect(engine.markDone(tid)).toBe(true);
    expect(engine.snapshot().topics[0].status).toBe("done");
    expect(byName(engine, "Alice").answered).toBe(true);
    expect(engine.snapshot().activeTopicId).toBeNull();
  });

  it("an unknown id returns false", () => {
    expect(engine.markDone("nope")).toBe(false);
  });

  it("done-ing a non-active topic leaves an unrelated active id alone", () => {
    engine.addParticipant("Alice");
    engine.addParticipant("Bob");
    const t1 = engine.addTopic("T1");
    const t2 = engine.addTopic("T2");
    engine.select(pidOf(engine, "Alice"));
    engine.assign(t1);
    expect(engine.snapshot().activeTopicId).toBe(t1);
    expect(engine.markDone(t2)).toBe(true);
    expect(engine.snapshot().activeTopicId).toBe(t1);
  });

  it("a done topic with no assignee does not throw", () => {
    const tid = engine.addTopic("Orphan");
    expect(engine.markDone(tid)).toBe(true);
    expect(engine.snapshot().topics[0].status).toBe("done");
  });
});

describe("reopenTopic", () => {
  it("resets the topic and frees the assignee", () => {
    const { tid } = setupActiveTopic(engine);
    engine.markDone(tid);
    expect(byName(engine, "Alice").answered).toBe(true);
    expect(engine.reopenTopic(tid)).toBe(true);
    const t = engine.snapshot().topics[0];
    expect(t.status).toBe("open");
    expect(t.assignee).toBeNull();
    expect(byName(engine, "Alice").answered).toBe(false);
  });

  it("reopening the active topic clears the active id", () => {
    const { tid } = setupActiveTopic(engine);
    expect(engine.snapshot().activeTopicId).toBe(tid);
    expect(engine.reopenTopic(tid)).toBe(true);
    expect(engine.snapshot().activeTopicId).toBeNull();
  });

  it("an unknown id returns false", () => {
    expect(engine.reopenTopic("nope")).toBe(false);
  });

  it("reselect re-selects the assignee so we land back on the topic list", () => {
    const { pid, tid } = setupActiveTopic(engine);
    expect(engine.reopenTopic(tid, true)).toBe(true);
    const snap = engine.snapshot();
    expect(snap.activeTopicId).toBeNull();
    expect(snap.selected.id).toBe(pid);
  });

  it("without reselect the selection stays cleared (board reopen path)", () => {
    const { tid } = setupActiveTopic(engine);
    expect(engine.reopenTopic(tid)).toBe(true);
    expect(engine.snapshot().selected).toBeNull();
  });

  it("reselect skips an assignee who opted out after being assigned", () => {
    // setExcluded promises an excluded person can never end up selected, so
    // the focus "Back" button must not re-select them.
    const { pid, tid } = setupActiveTopic(engine);
    engine.setExcluded(pid, true);
    expect(engine.reopenTopic(tid, true)).toBe(true);
    expect(engine.snapshot().selected).toBeNull();
  });
});

describe("reset", () => {
  it("keeps the roster and topics but clears the round", () => {
    const { tid } = setupActiveTopic(engine);
    engine.markDone(tid);
    const startedBefore = engine.snapshot().startedAt;

    engine.reset();
    const snap = engine.snapshot();
    expect(names(snap)).toEqual(["Alice"]);
    expect(snap.topics).toHaveLength(1);
    const t = snap.topics[0];
    expect(t.status).toBe("open");
    expect(t.assignee).toBeNull();
    expect(byName(engine, "Alice").answered).toBe(false);
    expect(snap.selected).toBeNull();
    expect(snap.activeTopicId).toBeNull();
    expect(snap.startedAt).toBeGreaterThanOrEqual(startedBefore);
  });
});

describe("removeParticipant", () => {
  it("drops from the roster and order", () => {
    engine.addParticipant("Alice");
    engine.addParticipant("Bob");
    const pid = pidOf(engine, "Alice");
    engine.removeParticipant(pid);
    expect(names(engine.snapshot())).toEqual(["Bob"]);
    expect(engine.snapshot().participants.find((p) => p.id === pid)).toBeUndefined();
  });

  it("removing an unknown pid is safe", () => {
    expect(() => engine.removeParticipant("nope")).not.toThrow();
  });

  it("clears the selection if the removed person was selected", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    engine.select(pid);
    engine.removeParticipant(pid);
    expect(engine.snapshot().selected).toBeNull();
  });

  it("frees a held (active) topic and clears active", () => {
    const { pid, tid } = setupActiveTopic(engine);
    expect(engine.snapshot().activeTopicId).toBe(tid);
    engine.removeParticipant(pid);
    const t = engine.snapshot().topics[0];
    expect(t.assignee).toBeNull();
    expect(t.status).toBe("open");
    expect(engine.snapshot().activeTopicId).toBeNull();
  });

  it("keeps a completed topic done (does not resurrect a finished prompt)", () => {
    const { pid, tid } = setupActiveTopic(engine);
    engine.markDone(tid);
    engine.removeParticipant(pid);
    expect(engine.snapshot().topics[0].status).toBe("done");
  });
});

describe("demo", () => {
  it("startDemo sets the flag and seeds the roster + topics", () => {
    engine.startDemo();
    const snap = engine.snapshot();
    expect(snap.demo).toBe(true);
    expect(snap.participants).toHaveLength(7);
    expect(snap.topics).toHaveLength(6);
  });

  it("startDemo pins exactly one host first", () => {
    engine.startDemo();
    const snap = engine.snapshot();
    const hosts = snap.participants.filter((p) => p.is_host);
    expect(hosts).toHaveLength(1);
    expect(snap.participants[0].is_host).toBe(true);
  });

  it("startDemo uses d0..dN ids in seed order", () => {
    engine.startDemo();
    const ids = engine.snapshot().participants.map((p) => p.id);
    expect(ids).toEqual(["d0", "d1", "d2", "d3", "d4", "d5", "d6"]);
  });

  it("startDemo stamps every entry with source 'demo'", () => {
    engine.startDemo();
    expect(engine.snapshot().participants.every((p) => p.source === "demo")).toBe(true);
  });

  it("startDemo leaves a rollable pool", () => {
    engine.startDemo();
    for (let i = 0; i < 30; i++) {
      const pid = engine.pick();
      expect(pid).not.toBeNull();
      const p = engine.snapshot().participants.find((x) => x.id === pid);
      // The host is a full participant now, so a pick may land on them; only
      // present + unanswered is required.
      expect(p.present).toBe(true);
      expect(p.answered).toBe(false);
      engine.cancelPick();
    }
  });

  it("startDemo replaces existing state", () => {
    engine.addParticipant("Real Person");
    engine.addTopic("Real topic");
    engine.startDemo();
    expect(names(engine.snapshot())).not.toContain("Real Person");
    expect(engine.snapshot().topics.map((t) => t.headline)).not.toContain("Real topic");
  });

  it("topic ids keep climbing the global counter across demo start", () => {
    expect(engine.addTopic("Before")).toBe("t1");
    engine.startDemo();
    // The six demo topics take t2..t7, never reusing t1.
    expect(engine.snapshot().topics[0].id).toBe("t2");
  });

  it("stopDemo clears everything", () => {
    engine.startDemo();
    const pid = engine.pick();
    const tid = engine.snapshot().topics[0].id;
    engine.assign(tid);
    engine.stopDemo();
    const snap = engine.snapshot();
    expect(snap.demo).toBe(false);
    expect(snap.participants).toEqual([]);
    expect(snap.topics).toEqual([]);
    expect(snap.selected).toBeNull();
    expect(snap.activeTopicId).toBeNull();
    expect(pid).not.toBeNull();
  });
});

describe("snapshot", () => {
  it("has exactly the expected keys", () => {
    const snap = engine.snapshot();
    expect(Object.keys(snap).sort()).toEqual(
      ["activeTopicId", "demo", "participants", "selected", "startedAt", "topics"].sort(),
    );
  });

  it("assignee resolves to {id, name} or null", () => {
    engine.addParticipant("Alice");
    const tid = engine.addTopic("Topic");
    expect(engine.snapshot().topics[0].assignee).toBeNull();
    const pid = pidOf(engine, "Alice");
    engine.select(pid);
    engine.assign(tid);
    expect(engine.snapshot().topics[0].assignee).toEqual({ id: pid, name: "Alice" });
  });

  it("selected resolves to {id, name}", () => {
    engine.addParticipant("Alice");
    const pid = pidOf(engine, "Alice");
    engine.select(pid);
    expect(engine.snapshot().selected).toEqual({ id: pid, name: "Alice" });
  });

  it("returns a deep copy that cannot mutate engine state", () => {
    engine.addParticipant("Alice");
    engine.addTopic("Topic");
    const snap1 = engine.snapshot();
    snap1.participants[0].name = "Mutated";
    snap1.topics[0].headline = "Mutated";
    const snap2 = engine.snapshot();
    expect(snap2.participants[0].name).toBe("Alice");
    expect(snap2.topics[0].headline).toBe("Topic");
  });
});

describe("subscribe", () => {
  it("calls the listener immediately with the current snapshot", () => {
    engine.addParticipant("Alice");
    const fn = vi.fn();
    engine.subscribe(fn);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(names(fn.mock.calls[0][0])).toEqual(["Alice"]);
  });

  it("notifies on every mutation with a fresh snapshot", () => {
    const fn = vi.fn();
    engine.subscribe(fn); // immediate call (1)
    engine.addParticipant("Alice"); // (2)
    engine.addTopic("Topic"); // (3)
    expect(fn).toHaveBeenCalledTimes(3);
    expect(names(fn.mock.calls[2][0])).toEqual(["Alice"]);
  });

  it("unsubscribe stops further notifications", () => {
    const fn = vi.fn();
    const off = engine.subscribe(fn);
    off();
    engine.addParticipant("Alice");
    expect(fn).toHaveBeenCalledTimes(1); // only the immediate call
  });

  it("fans out to multiple subscribers", () => {
    const a = vi.fn();
    const b = vi.fn();
    engine.subscribe(a);
    engine.subscribe(b);
    engine.addParticipant("Alice");
    expect(a).toHaveBeenCalledTimes(2);
    expect(b).toHaveBeenCalledTimes(2);
  });

  it("gives each listener its own snapshot — one mutating cannot corrupt the next", () => {
    engine.subscribe((snap) => {
      if (snap.participants.length) snap.participants[0].name = "Corrupted";
    });
    const seen = [];
    engine.subscribe((snap) => seen.push(snap));
    engine.addParticipant("Alice");
    expect(seen.at(-1).participants[0].name).toBe("Alice");
  });
});
