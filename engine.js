// Browser-side, DOM-free port of board.py's `State` class. It produces the
// exact same snapshot shape the Python server pushes over SSE, so app.js can
// drive a fully static (manual-mode) board with no server at all.
//
// Nothing here touches the DOM or runs on import, so it's unit-testable under
// jsdom. Unlike the server there are no auto-read ("a"-prefixed) participants
// or host syncing: a static board is manual-only. Everything else (the pick
// pool rules, the assign/done/reopen lifecycle, the demo seed) mirrors the
// server one-for-one.

// ---- demo seed data (verbatim from board.py) ---------------------
// name, is_host. The host runs the board and is skipped by the random roll.
const DEMO_PARTICIPANTS = [
  ["Sam Rivera", true],
  ["Maya Chen", false],
  ["Diego Santos", false],
  ["Priya Patel", false],
  ["Logan Brooks", false],
  ["Aisha Okafor", false],
  ["Noah Kim", false],
];

const DEMO_TOPICS = [
  {
    headline: "What's a small win you had this week?",
    details: "Anything counts. Keep it to a minute or so.",
  },
  {
    headline: "If you could instantly master one skill, what would it be?",
    details: "",
  },
  {
    headline: "Describe a place you'd happily go back to.",
    details: "Tell us what makes it worth a second visit.",
  },
  { headline: "What's the best advice you never took?", details: "" },
  { headline: "What everyday thing are you quietly great at?", details: "" },
  {
    headline: "If this week had a theme song, what would it be?",
    details: "No wrong answers. Bonus points for humming a bar.",
  },
];

export function createEngine() {
  // --- internal state (mirrors State.__init__) -------------------------
  let startedAt = Date.now();
  const participants = new Map(); // id -> participant record
  let order = []; // participant ids in display order
  const topics = new Map(); // id -> topic record
  let topicOrder = []; // topic ids in display order
  let selectedPid = null; // rolled person awaiting a topic
  let activeTopicId = null; // topic currently on the focus view
  let demo = false; // true while the sample meeting is loaded
  let topicSeq = 0; // monotonic, never reused even across reset/demo
  let manualSeq = 0; // makes each manual add a distinct id, even for dup names
  const listeners = new Set();

  // --- id helpers ------------------------------------------------------
  function newTopicId() {
    topicSeq += 1;
    return `t${topicSeq}`;
  }

  // Each manual add gets a fresh unique id even when the name repeats, so two
  // people called "Alex" are two distinct entries (board.py folds time into
  // the id for the same effect).
  function newManualId() {
    manualSeq += 1;
    return `m${manualSeq}`;
  }

  // --- snapshot --------------------------------------------------------
  function topicView(t) {
    let assignee = null;
    const aid = t.assignee;
    if (aid && participants.has(aid)) {
      const ap = participants.get(aid);
      assignee = { id: ap.id, name: ap.name };
    }
    return {
      id: t.id,
      headline: t.headline,
      details: t.details,
      status: t.status,
      assignee,
    };
  }

  // A fresh, fully-detached snapshot every call (no shared references), so a
  // caller mutating what it gets back can never corrupt engine state.
  function snapshot() {
    const ordered = [];
    for (const pid of order) {
      const p = participants.get(pid);
      if (p) ordered.push({ ...p });
    }
    // Defensive: include any participant somehow not in order at the end.
    for (const [pid, p] of participants) {
      if (!order.includes(pid)) ordered.push({ ...p });
    }
    const topicSnaps = [];
    for (const tid of topicOrder) {
      if (topics.has(tid)) topicSnaps.push(topicView(topics.get(tid)));
    }
    let selected = null;
    if (selectedPid && participants.has(selectedPid)) {
      const sp = participants.get(selectedPid);
      selected = { id: sp.id, name: sp.name };
    }
    return {
      startedAt,
      participants: ordered,
      topics: topicSnaps,
      selected,
      activeTopicId,
      demo,
    };
  }

  // --- subscription / notify ------------------------------------------
  function notify() {
    const snap = snapshot();
    for (const fn of listeners) fn(snap);
  }

  // Register a listener. Like the SSE server pushing current state on connect,
  // fire once immediately with the current snapshot, then on every mutation.
  function subscribe(fn) {
    listeners.add(fn);
    fn(snapshot());
    return function unsubscribe() {
      listeners.delete(fn);
    };
  }

  // --- participant mutations ------------------------------------------
  function addParticipant(name) {
    const nm = String(name || "").trim();
    if (!nm) return;
    const pid = newManualId();
    participants.set(pid, {
      id: pid,
      name: nm,
      joinTime: Date.now(),
      leftTime: null,
      present: true,
      answered: false,
      is_host: false,
    });
    order.push(pid);
    notify();
  }

  // Drop a participant. Like board.py, an unknown pid is a safe no-op that
  // still broadcasts the (unchanged) snapshot.
  function removeParticipant(pid) {
    participants.delete(pid);
    order = order.filter((id) => id !== pid);
    if (selectedPid === pid) selectedPid = null;
    // Free any in-progress topic this person held: an active topic can't keep a
    // removed assignee. Completed (done) topics stay done so tidying the roster
    // doesn't resurrect a finished prompt and make it eligible again this round.
    for (const t of topics.values()) {
      if (t.assignee === pid && t.status !== "done") {
        t.assignee = null;
        t.status = "open";
        if (activeTopicId === t.id) activeTopicId = null;
      }
    }
    notify();
  }

  // --- topic mutations -------------------------------------------------
  function makeTopic(headline, details) {
    const tid = newTopicId();
    topics.set(tid, {
      id: tid,
      headline,
      details,
      status: "open",
      assignee: null,
    });
    topicOrder.push(tid);
    return tid;
  }

  function addTopic(headline, details = "") {
    const h = String(headline || "").trim();
    if (!h) return null;
    const tid = makeTopic(h, String(details || "").trim());
    notify();
    return tid;
  }

  // Bulk add. With replace=true the whole topic set is cleared first (used by
  // the localStorage re-seed and the "clear & reload" path).
  function addTopics(items, replace = false) {
    let added = 0;
    if (replace) {
      topics.clear();
      topicOrder = [];
      activeTopicId = null;
      // A pending roll has nothing left to be assigned to; drop it so the
      // client doesn't strand on the picking view with 0 topics.
      selectedPid = null;
    }
    for (const raw of items || []) {
      const it = raw && typeof raw === "object" ? raw : {};
      const h = String(it.headline || "").trim();
      if (!h) continue;
      makeTopic(h, String(it.details || "").trim());
      added += 1;
    }
    notify();
    return added;
  }

  function editTopic(tid, headline, details) {
    const h = String(headline || "").trim();
    if (!h) return false;
    const t = topics.get(tid);
    if (!t) return false;
    t.headline = h;
    t.details = String(details || "").trim();
    notify();
    return true;
  }

  function removeTopic(tid) {
    if (!topics.has(tid)) return false;
    topics.delete(tid);
    topicOrder = topicOrder.filter((id) => id !== tid);
    if (activeTopicId === tid) activeTopicId = null;
    notify();
    return true;
  }

  // --- selection & assignment -----------------------------------------
  // Participants who can be rolled: present, not yet answered, not the host
  // (the host runs the board), and not the just-excluded person.
  function eligiblePool(excludePid) {
    const pool = [];
    for (const pid of order) {
      const p = participants.get(pid);
      if (!p?.present || p.answered || p.is_host) continue;
      if (pid === excludePid) continue;
      pool.push(pid);
    }
    return pool;
  }

  // Roll a random eligible participant into `selected`. Returns the id, or null
  // if nobody is eligible. `excludePid` powers "pick someone else", but if that
  // empties the pool we fall back to allowing them again.
  function pick(excludePid) {
    let pool = eligiblePool(excludePid);
    if (!pool.length && excludePid !== undefined && excludePid !== null) {
      pool = eligiblePool(undefined);
    }
    let chosen;
    if (!pool.length) {
      selectedPid = null;
      chosen = null;
    } else {
      chosen = pool[Math.floor(Math.random() * pool.length)];
      selectedPid = chosen;
    }
    notify();
    return chosen;
  }

  // Manually select a specific present participant (the host included, since
  // they're skipped by the random roll) so the host can hand themselves, or
  // anyone, a topic. Someone who already had their turn this round is rejected,
  // the same one-turn rule the random roll uses.
  function select(pid) {
    const p = participants.get(pid);
    if (!p?.present || p.answered) return false;
    selectedPid = pid;
    notify();
    return true;
  }

  function cancelPick() {
    selectedPid = null;
    notify();
  }

  // Give the currently selected person an open topic. Locks the topic
  // (status -> active) and makes it the focus view.
  function assign(tid) {
    const sid = selectedPid;
    const p = sid ? participants.get(sid) : null;
    if (!p?.present) {
      // No selection, or the selected person left before a topic was handed to
      // them: drop the stale selection.
      selectedPid = null;
      notify();
      return false;
    }
    const t = topics.get(tid);
    if (t?.status !== "open") {
      notify();
      return false;
    }
    t.assignee = sid;
    t.status = "active";
    activeTopicId = tid;
    selectedPid = null;
    notify();
    return true;
  }

  function markDone(tid) {
    const t = topics.get(tid);
    if (!t) return false;
    t.status = "done";
    const aid = t.assignee;
    if (aid && participants.has(aid)) participants.get(aid).answered = true;
    if (activeTopicId === tid) activeTopicId = null;
    notify();
    return true;
  }

  // Undo an active/done topic back to open (the focus "Back" button and the
  // board "reopen" affordance). The assignee returns to the pool.
  function reopenTopic(tid) {
    const t = topics.get(tid);
    if (!t) return false;
    const aid = t.assignee;
    if (aid && participants.has(aid)) participants.get(aid).answered = false;
    t.assignee = null;
    t.status = "open";
    if (activeTopicId === tid) activeTopicId = null;
    notify();
    return true;
  }

  // New round: keep the topics and the roster, but clear every assignment and
  // answered flag so the same set can run again.
  function reset() {
    startedAt = Date.now();
    for (const p of participants.values()) p.answered = false;
    for (const t of topics.values()) {
      t.assignee = null;
      t.status = "open";
    }
    selectedPid = null;
    activeTopicId = null;
    notify();
  }

  // --- demo mode -------------------------------------------------------
  // Clear the whole meeting: roster, topics, and any in-flight round.
  function wipe() {
    participants.clear();
    order = [];
    topics.clear();
    topicOrder = [];
    selectedPid = null;
    activeTopicId = null;
    startedAt = Date.now();
  }

  // Load the sample meeting so a first-time host can try the flow. Demo
  // participants get "d0, d1, ..." ids (in seed order) so they're never
  // confused with manual ("m") entries. Topic ids keep climbing the global
  // monotonic counter.
  function startDemo() {
    wipe();
    demo = true;
    DEMO_PARTICIPANTS.forEach(([name, isHost], i) => {
      const pid = `d${i}`;
      participants.set(pid, {
        id: pid,
        name,
        joinTime: Date.now(),
        leftTime: null,
        present: true,
        answered: false,
        is_host: isHost,
      });
      order.push(pid);
    });
    for (const t of DEMO_TOPICS) makeTopic(t.headline, t.details || "");
    notify();
  }

  // Exit the demo back to a clean slate.
  function stopDemo() {
    wipe();
    demo = false;
    notify();
  }

  return {
    snapshot,
    subscribe,
    addParticipant,
    removeParticipant,
    addTopic,
    addTopics,
    editTopic,
    removeTopic,
    assign,
    markDone,
    reopenTopic,
    pick,
    select,
    cancelPick,
    reset,
    startDemo,
    stopDemo,
  };
}
