import { createEngine } from "./engine.js";
import {
  cardClass,
  chipClass,
  clearStoredTopics,
  eligibleNames,
  escapeHtml,
  fmtTime,
  initials,
  loadOnboarded,
  loadStoredTopics,
  newlyDoneId,
  nextView,
  parsePaste,
  pickHint,
  saveOnboarded,
  saveStoredTopics,
  showWelcome,
  topicAux,
} from "./lib.js";

// ---- icons (inline so a single file ships) -----------------------
const ICON_X = `<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>`;
const ICON_EDIT = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 2.5l2.5 2.5M9.5 4L3 10.5V13h2.5L12 6.5z"/></svg>`;
const ICON_TRASH = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 4.5h10M6 4.5V3h4v1.5M5 4.5l.6 8h4.8l.6-8"/></svg>`;
const ICON_REOPEN = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8a5 5 0 1 1 1.5 3.5M3 8V5M3 8h3"/></svg>`;
const ICON_DONE = `<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5l3 3 7-7"/></svg>`;
const ICON_PERSON = `<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="5" r="2.5"/><path d="M3.5 13a4.5 4.5 0 0 1 9 0"/></svg>`;
const ICON_DOT = `<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3.2" fill="currentColor"/></svg>`;
const ICON_OPEN = `<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="8" cy="8" r="4.5"/></svg>`;

const $ = (id) => document.getElementById(id);
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- API ---------------------------------------------------------
// One app.js, two transports. With a backend present (uv run board.py) we POST
// to /api/* and stream snapshots over SSE, preserving Zoom auto-read. Served
// statically (GitHub Pages) we drive a local engine.js with no network at all.
// The transport is chosen once at startup; every post() below delegates to it.
let activeTransport = null;
// The transport is chosen asynchronously at startup (we probe for a backend).
// Until it resolves, buffer posts on this promise instead of dropping them, so
// an early click during the probe still reaches the engine/server.
let markTransportReady;
const transportReady = new Promise((resolve) => {
  markTransportReady = resolve;
});
function post(url, body) {
  return activeTransport
    ? activeTransport.post(url, body)
    : transportReady.then((t) => t.post(url, body));
}

// ---- state cache -------------------------------------------------
let state = {
  startedAt: Date.now(),
  participants: [],
  topics: [],
  selected: null,
  activeTopicId: null,
};

// ---- localStorage seed guard (topic storage lives in lib.js) -----
let seededThisLoad = false;

// Whether this browser has seen the first-run welcome. Held in memory so a
// dismiss re-renders instantly; mirrored to localStorage so it sticks.
let onboarded = loadOnboarded();

// ====================================================================
//  RENDER  — derive the active view purely from snapshot state.
//    activeTopicId != null  -> FOCUS
//    selected != null       -> PICKING
//    else                   -> BOARD
// ====================================================================
// The id of a topic that just transitioned to "done" this snapshot, so the
// board can give it a one-shot completion animation.
let justDoneId = null;

// Completion firework: a spark burst in the Toastmasters palette erupting from
// the finished card. Pure DOM, no library; particles self-remove.
const BURST_COLORS = ["#f2df74", "#f6e58a", "#006094", "#004165", "#772432", "#ffffff"];

// A spark burst + shockwave ring centered on (ox, oy). Pure DOM; particles
// self-remove. `scale` widens the spread for bigger moments (the reveal).
function spawnBurst(ox, oy, { count = 26, scale = 1 } = {}) {
  const layer = document.createElement("div");
  layer.className = "celebrate-layer";

  const ring = document.createElement("div");
  ring.className = "celebrate-ring";
  ring.style.left = `${ox}px`;
  ring.style.top = `${oy}px`;
  layer.appendChild(ring);

  for (let i = 0; i < count; i++) {
    const bit = document.createElement("i");
    bit.className = `celebrate-bit${i % 3 === 0 ? " spark" : ""}`;
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.45;
    const dist = (95 + Math.random() * 160) * scale;
    const tx = Math.cos(angle) * dist;
    const ty = Math.sin(angle) * dist + dist * 0.35; // slight gravity bias
    const size = 6 + Math.random() * 7;
    bit.style.left = `${ox}px`;
    bit.style.top = `${oy}px`;
    bit.style.width = bit.style.height = `${size.toFixed(1)}px`;
    bit.style.background = BURST_COLORS[i % BURST_COLORS.length];
    bit.style.setProperty("--tx", `${tx.toFixed(1)}px`);
    bit.style.setProperty("--ty", `${ty.toFixed(1)}px`);
    bit.style.setProperty("--rot", `${(Math.random() * 540 - 270).toFixed(0)}deg`);
    bit.style.setProperty("--dur", `${(950 + Math.random() * 550).toFixed(0)}ms`);
    bit.style.setProperty("--delay", `${(Math.random() * 70).toFixed(0)}ms`);
    layer.appendChild(bit);
  }

  document.body.appendChild(layer);
  setTimeout(() => layer.remove(), 1800);
}

// Completion firework from the just-finished card.
function celebrateCard(cardEl) {
  if (reduceMotion()) return;
  const rect = cardEl.getBoundingClientRect();
  spawnBurst(rect.left + rect.width / 2, rect.top + rect.height * 0.42);
}

// The reveal landing: a wider burst erupts from the settled name as the
// spotlight blooms, so the pick feels like an entrance, not just a label.
function celebrateReveal() {
  if (reduceMotion()) return;
  const rect = $("shuffleName").getBoundingClientRect();
  spawnBurst(rect.left + rect.width / 2, rect.top + rect.height / 2, { count: 34, scale: 1.3 });
}

// Leaving the picking view: tear down any in-flight reveal so re-picking the
// same person later (e.g. after Cancel) still triggers a fresh shuffle.
function resetReveal() {
  clearShuffle();
  clearTopicRoll();
  $("stage").classList.remove("lit");
  lastSelectedId = null;
  revealActive = false;
}

function render(s) {
  const prev = state;
  // Cinematic handoff: when a topic is assigned (picking -> focus), morph the
  // big settled name into the focus-view hero via the View Transitions API, so
  // the spotlight visibly "follows" the speaker. Falls back to a plain switch
  // where the API is missing or motion is reduced.
  const morph =
    nextView(prev) === "picking" &&
    nextView(s) === "focus" &&
    typeof document.startViewTransition === "function" &&
    !reduceMotion();
  if (morph) document.startViewTransition(() => applyRender(s, prev));
  else applyRender(s, prev);
}

function applyRender(s, prev) {
  state = s;

  // A single topic flipping to done (host hit "Done") gets a celebration.
  const done = newlyDoneId(prev.topics, s.topics);
  if (done) justDoneId = done;

  const view = nextView(s);
  $("board").hidden = view !== "board";
  $("stage").hidden = view !== "picking";
  $("focus").hidden = view !== "focus";

  if (view !== "picking") resetReveal();

  RENDERERS[view](s);

  // Persist the topic set whenever it changes, and one-time re-seed
  // from localStorage if the server starts empty.
  syncTopicStorage(s);
}

// Hidden/shown above; this maps the resolved view to its renderer.
const RENDERERS = { board: renderBoard, picking: renderPicking, focus: renderFocus };

// ---- topic localStorage sync + one-time re-seed ------------------
function syncTopicStorage(s) {
  // Sample topics live only on the server. Never mirror them into the host's
  // saved set, and don't re-seed from storage on top of a running demo —
  // marking this load "seeded" keeps the post-exit clean slate clean too.
  if (s.demo) {
    seededThisLoad = true;
    return;
  }

  const serverTopics = s.topics.map((t) => ({ headline: t.headline, details: t.details || "" }));

  if (!seededThisLoad) {
    // First snapshot this page load. If the server is empty, re-seed it once
    // from whatever this browser remembered; otherwise adopt the server set.
    seededThisLoad = true; // guard before the async call to avoid loops
    if (serverTopics.length === 0) {
      const stored = loadStoredTopics();
      if (stored.length > 0) {
        post("/api/topics", { topics: stored, replace: false });
      }
      return; // don't clobber the cache mid-reseed
    }
  }

  // After the initial seed, mirror the server's set on every snapshot —
  // INCLUDING when it becomes empty — so deleting the last topic isn't
  // resurrected from a stale cache on the next reload.
  saveStoredTopics(serverTopics);
}

// ---- topic card markup (shared by board + picking choices) -------
function cardStatusTag(t) {
  if (t.status === "done") return `<span class="status-tag">${ICON_DONE}Done</span>`;
  if (t.status === "active") return `<span class="status-tag">${ICON_DOT}On now</span>`;
  return `<span class="status-tag">${ICON_OPEN}Open</span>`;
}

// The detail is a surprise: hidden on open cards, revealed only once the topic
// is chosen (the focus view, and afterward on the done/active card).
function cardDetails(t) {
  return t.details && t.status !== "open" ? `<div class="dt">${escapeHtml(t.details)}</div>` : "";
}

function cardAssignee(t) {
  return t.assignee
    ? `<div class="assignee">${ICON_PERSON}<span class="who">${escapeHtml(t.assignee.name)}</span></div>`
    : "";
}

// Open cards (board only) get edit + remove — never in pick "choose" mode.
function cardTools(t, opts) {
  if (opts.pickMode || t.status !== "open") return "";
  return (
    `<div class="card-tools">` +
    `<button class="tool" type="button" data-act="edit" data-tid="${t.id}" aria-label="Edit topic">${ICON_EDIT}</button>` +
    `<button class="tool danger" type="button" data-act="remove-topic" data-tid="${t.id}" aria-label="Remove topic">${ICON_TRASH}</button>` +
    `</div>`
  );
}

// Done/active cards get a reopen link — never in pick "choose" mode.
function cardReopen(t, opts) {
  if (opts.pickMode || (t.status !== "done" && t.status !== "active")) return "";
  return `<button class="reopen-link" type="button" data-act="reopen" data-tid="${t.id}">${ICON_REOPEN}<span>Reopen</span></button>`;
}

function topicCard(t, opts = {}) {
  const choose = !!opts.choose && t.status === "open";
  const lockedOut = !!opts.pickMode && t.status !== "open";
  const inner =
    cardStatusTag(t) +
    `<div class="hl">${escapeHtml(t.headline)}</div>` +
    cardDetails(t) +
    cardAssignee(t) +
    cardReopen(t, opts);
  const cls = cardClass(t.status, choose, lockedOut);
  if (choose) {
    // A real button so it's keyboard-operable; click assigns the topic.
    return `<button class="${cls}" type="button" data-act="assign" data-tid="${t.id}">${inner}</button>`;
  }
  // Static card (board open/active/done, or picking locked-out).
  return `<div class="${cls}" data-tid="${t.id}">${cardTools(t, opts)}${inner}</div>`;
}

// ============================== BOARD ==============================
// One-shot celebration for the card that just flipped to done.
function celebrateNewlyDone(host) {
  if (!justDoneId) return;
  const doneCard = host.querySelector(`.card.done[data-tid="${justDoneId}"]`);
  justDoneId = null; // consume it — this render only
  if (!doneCard || reduceMotion()) return;
  requestAnimationFrame(() => {
    doneCard.classList.add("just-done");
    celebrateCard(doneCard);
  });
}

function renderBoard(s) {
  $("since").textContent = fmtTime(s.startedAt);

  // First-run welcome vs. running demo vs. normal board. The welcome only
  // shows on a cold start; the demo banner shows whenever sample data is live.
  const welcome = showWelcome(s, onboarded);
  $("board").classList.toggle("first-run", welcome);
  $("welcome").hidden = !welcome;
  $("demoBar").hidden = !s.demo;

  const present = s.participants.filter((p) => p.present);
  const answered = present.filter((p) => p.answered).length;
  // "Still to go" mirrors the server pool: present, not answered, not host.
  const toGo = present.filter((p) => !p.answered && !p.is_host).length;
  const tDone = s.topics.filter((t) => t.status === "done").length;
  const tTotal = s.topics.length;
  const openCount = s.topics.filter((t) => t.status === "open").length;

  $("s-togo").textContent = toGo;
  $("s-answered").textContent = answered;
  $("s-room").textContent = present.length;
  $("s-tdone").textContent = tDone;
  $("s-ttotal").textContent = tTotal;
  $("topicsAux").textContent = topicAux({ tTotal, openCount, tDone });

  const host = $("topicsHost");
  if (tTotal === 0) {
    host.innerHTML = `<div class="topic-empty">
           <h3>No topics yet</h3>
           <p>They live only in this browser. Add one, or paste a whole list at once.</p>
           <button class="btn" type="button" data-act="open-add">Add topics</button>
         </div>`;
  } else {
    host.innerHTML = `<div class="topics">${s.topics.map((t) => topicCard(t, {})).join("")}</div>`;
  }
  celebrateNewlyDone(host);

  renderRoster(s);

  // Primary CTA: toGo is exactly the pick-eligible pool (present, !answered, !host).
  const hasOpen = openCount > 0;
  $("pickBtn").disabled = toGo === 0 || !hasOpen;
  $("pickHint").textContent = pickHint({ toGo, answered, hasOpen });
}

function rosterStateIcon(p) {
  if (!p.present) return ICON_DOT;
  if (p.answered) return `<span class="state-ic done">${ICON_DONE}</span>`;
  return `<span class="state-ic present">${ICON_OPEN}</span>`;
}

function rosterChip(p) {
  // Clicking a present name manually selects them (host included). Someone who
  // already had their turn isn't selectable — same one-turn rule as the random
  // roll, and the server rejects it anyway.
  const canSelect = p.present && !p.answered;
  const hostPill = p.is_host ? `<span class="host-pill">host</span>` : "";
  const nameBtn =
    `<button class="pick-name" type="button" ${canSelect ? "" : "disabled"} data-act="select" data-pid="${p.id}">` +
    rosterStateIcon(p) +
    `<span class="who">${escapeHtml(p.name)}</span>` +
    hostPill +
    `</button>`;
  const removeBtn = `<button class="x" type="button" data-act="remove-p" data-pid="${p.id}" aria-label="Remove ${escapeHtml(p.name)}">${ICON_X}</button>`;
  return `<span class="${chipClass(p)}">${nameBtn}${removeBtn}</span>`;
}

function renderRoster(s) {
  const roster = $("roster");
  if (!s.participants.length) {
    roster.innerHTML = `<div class="empty" style="width:100%">No one yet. Joins appear automatically, or add someone below.</div>`;
    return;
  }
  roster.innerHTML = s.participants.map(rosterChip).join("");
}

// ============================= PICKING =============================
let shuffleTimer = null;
let shuffleTimeout = null;
let lastSelectedId = null;
let revealActive = false;

function clearShuffle() {
  if (shuffleTimer) {
    clearInterval(shuffleTimer);
    shuffleTimer = null;
  }
  if (shuffleTimeout) {
    clearTimeout(shuffleTimeout);
    shuffleTimeout = null;
  }
}

// ---- Press-Your-Luck topic randomizer -----------------------------
let topicRolling = false;
let topicRollTimer = null;

function clearTopicRoll() {
  if (topicRollTimer) {
    clearTimeout(topicRollTimer);
    topicRollTimer = null;
  }
  topicRolling = false;
  $("stage").classList.remove("rolling");
  const rb = $("randomTopicBtn");
  if (rb) rb.disabled = false;
  const pa = $("pickAgainBtn");
  if (pa) pa.disabled = false;
  document
    .querySelectorAll("#pickTopicsHost .card.flash, #pickTopicsHost .card.flash-final")
    .forEach((c) => {
      c.classList.remove("flash", "flash-final");
    });
}

// Hop a highlight across the open topic boxes, decelerate, land on a random
// open one, then assign it. Reduced motion skips straight to the pick.
function randomizeTopic() {
  if (topicRolling) return;
  const cards = [...document.querySelectorAll("#pickTopicsHost .card.choose")];
  if (!cards.length) return;
  startTopicRoll(cards, Math.floor(Math.random() * cards.length));
}

function startTopicRoll(cards, targetIdx) {
  const targetTid = cards[targetIdx].dataset.tid;
  const assign = () => {
    if (targetTid) post(`/api/topic/${targetTid}/assign`);
  };
  // Reduced motion or a single option: skip straight to the pick.
  if (reduceMotion() || cards.length === 1) return assign();

  topicRolling = true;
  $("stage").classList.add("rolling");
  $("randomTopicBtn").disabled = true;
  $("pickAgainBtn").disabled = true;

  const n = cards.length;
  const totalSteps = n * 2 + targetIdx + 1; // ~2 loops, then settle on target
  const minD = 70;
  const maxD = 360;
  let step = 0;

  const tick = () => {
    for (const c of cards) c.classList.remove("flash");
    const card = cards[step % n];
    card.classList.add("flash");
    step++;
    if (step >= totalSteps) {
      card.classList.add("flash-final");
      topicRollTimer = setTimeout(() => {
        topicRolling = false;
        assign();
      }, 520);
      return;
    }
    const t = step / totalSteps; // quadratic ease-out deceleration
    topicRollTimer = setTimeout(tick, minD + (maxD - minD) * t * t);
  };
  tick();
}

// Render the open topic cards as the choice grid. While a Press-Your-Luck roll
// animates, the grid is left in place so the highlight chase isn't wiped by an
// incoming snapshot.
function renderPickChoices(s) {
  const choices = s.topics
    .map((t) => topicCard(t, { pickMode: true, choose: t.status === "open" }))
    .join("");
  $("pickTopicsHost").innerHTML = s.topics.length
    ? `<div class="topics">${choices}</div>`
    : `<div class="empty" style="width:100%">No topics to assign. Cancel and add some first.</div>`;
  $("randomTopicBtn").disabled = s.topics.filter((t) => t.status === "open").length === 0;
}

// A brand-new selection plays the shuffle reveal; re-rendering onto an
// already-settled one (e.g. a topic was removed mid-pick) keeps the settled UI.
function applyReveal(s, sel, isNew) {
  if (isNew) startReveal(s, sel);
  else if (!revealActive) settleReveal(sel);
}

function renderPicking(s) {
  const sel = s.selected;
  $("stagePool").textContent = "";
  if (!topicRolling) renderPickChoices(s);

  const isNew = sel && sel.id !== lastSelectedId;
  lastSelectedId = sel ? sel.id : null;
  applyReveal(s, sel, isNew);
}

function startReveal(s, sel) {
  revealActive = true;
  clearShuffle();

  const nameEl = $("shuffleName");
  const label = $("shuffleLabel");
  const spark = $("spark");
  const banner = $("pickBanner");
  const choicesBox = $("pickChoices");

  // Reset staged elements.
  label.textContent = "Rolling…";
  label.style.visibility = "visible";
  spark.classList.remove("show");
  banner.classList.remove("show");
  choicesBox.classList.remove("show");
  nameEl.classList.remove("settled", "flourish");
  $("stage").classList.remove("lit"); // dim the spotlight while rolling

  if (reduceMotion()) {
    // Skip straight to the settled name — motion is never the only carrier.
    settleReveal(sel);
    revealActive = false;
    return;
  }

  // Cycle through eligible names rapidly, then settle on the real pick.
  let pool = eligibleNames(s).filter((n) => n); // names only
  if (!pool.length) pool = [sel.name];
  nameEl.classList.add("cycling");

  let i = 0;
  const flash = () => {
    nameEl.textContent = pool[i % pool.length];
    i++;
  };
  flash();
  shuffleTimer = setInterval(flash, 70);

  // After ~1s, settle. Keep the handle so a rapid re-pick can cancel it —
  // an orphaned timeout would settle on the previous person mid-animation.
  shuffleTimeout = setTimeout(() => {
    shuffleTimeout = null;
    clearShuffle();
    settleReveal(sel, true);
    revealActive = false;
  }, 1000);
}

function settleReveal(sel, burst = false) {
  clearShuffle();
  const nameEl = $("shuffleName");
  const label = $("shuffleLabel");
  const spark = $("spark");
  const banner = $("pickBanner");
  const choicesBox = $("pickChoices");

  nameEl.classList.remove("cycling");
  nameEl.classList.add("settled");
  nameEl.textContent = sel ? sel.name : "";
  if (!reduceMotion()) {
    // restart the pop animation
    nameEl.classList.remove("flourish");
    void nameEl.offsetWidth;
    nameEl.classList.add("flourish");
  }
  label.textContent = "It's";
  spark.classList.add("show");
  banner.innerHTML = sel ? `<b>${escapeHtml(sel.name)}</b> is up. Pick a topic.` : "";
  banner.classList.add("show");
  choicesBox.classList.add("show");
  $("stage").classList.add("lit"); // bloom the spotlight on the settled name
  if (burst && sel) celebrateReveal();
}

// ============================== FOCUS ==============================
function renderFocus(s) {
  const t = s.topics.find((x) => x.id === s.activeTopicId);
  if (!t) return; // snapshot will correct itself
  const who = t.assignee ? t.assignee.name : "";
  $("focusName").textContent = who;
  $("focusInitials").textContent = who ? initials(who) : "";
  $("focusHeadline").textContent = t.headline;
  const dt = $("focusDetails");
  if (t.details) {
    dt.textContent = t.details;
    dt.hidden = false;
  } else {
    dt.textContent = "";
    dt.hidden = true;
  }
  // Stash active id on the buttons for the click handlers.
  $("focusDoneBtn").dataset.tid = t.id;
  $("focusBackBtn").dataset.tid = t.id;
}

// ====================================================================
//  EVENT WIRING
// ====================================================================

// ---- Board: primary CTA + reset + clear --------------------------
$("pickBtn").addEventListener("click", () => {
  if ($("pickBtn").disabled) return;
  post("/api/pick", {});
});
$("resetBtn").addEventListener("click", () => {
  if (
    confirm("Start a new round? Topics and the roster are kept; everyone becomes eligible again.")
  )
    post("/api/reset");
});
$("clearTopicsBtn").addEventListener("click", () => {
  if (!confirm("Clear all topics? This removes them from the board and your browser.")) return;
  clearStoredTopics();
  post("/api/topics", { topics: [], replace: true });
});

// ---- First-run welcome + demo mode -------------------------------
// Mark the welcome seen so it never returns; remembered across visits.
function markOnboarded() {
  onboarded = true;
  saveOnboarded();
}
// "Try a quick demo": the server seeds the sample meeting and the snapshot it
// broadcasts re-renders us into demo mode.
$("demoStartBtn").addEventListener("click", () => {
  markOnboarded();
  post("/api/demo/start");
});
// "Set up my own board": no server change, so re-render the cached snapshot to
// drop the welcome and reveal the normal (empty) board.
$("demoSkipBtn").addEventListener("click", () => {
  markOnboarded();
  renderBoard(state);
});
// "Exit demo": wipe the sample meeting back to a clean slate. Only sample data
// is at stake, so no confirm — keep it one click.
$("demoExitBtn").addEventListener("click", () => post("/api/demo/stop"));

// ---- Add-topic tabs ----------------------------------------------
function showTab(which) {
  const single = which === "single";
  $("tabSingle").classList.toggle("on", single);
  $("tabPaste").classList.toggle("on", !single);
  $("tabSingle").setAttribute("aria-selected", String(single));
  $("tabPaste").setAttribute("aria-selected", String(!single));
  $("singleForm").hidden = !single;
  $("pasteForm").hidden = single;
}
$("tabSingle").addEventListener("click", () => showTab("single"));
$("tabPaste").addEventListener("click", () => showTab("paste"));

// ---- Add-topic editor toggle (collapsed by default) --------------
function setAddOpen(open) {
  $("addArea").hidden = !open;
  $("addToggle").setAttribute("aria-expanded", String(open));
  $("addToggleLabel").textContent = open ? "Hide topic editor" : "Add or edit topics";
}
function openAddEditor() {
  setAddOpen(true);
  $("addArea").scrollIntoView({
    behavior: reduceMotion() ? "auto" : "smooth",
    block: "nearest",
  });
  $("hl").focus();
}
$("addToggle").addEventListener("click", () => setAddOpen($("addArea").hidden));

// ---- Add one topic -----------------------------------------------
$("singleForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const headline = $("hl").value.trim();
  if (!headline) {
    $("hl").focus();
    return;
  }
  const details = $("dt").value.trim();
  $("hl").value = "";
  $("dt").value = "";
  $("hl").focus();
  await post("/api/topic", { headline, details });
});

// ---- Paste many ---------------------------------------------------
$("pasteForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const topics = parsePaste($("pasteBox").value);
  const replace = $("pasteReplace").checked;
  if (!topics.length && !replace) {
    $("pasteBox").focus();
    return;
  }
  $("pasteBox").value = "";
  $("pasteReplace").checked = false;
  await post("/api/topics", { topics, replace });
});

// ---- Roster: add / select / remove -------------------------------
$("rosterAddForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("rosterAddName");
  const name = input.value.trim();
  if (!name) return;
  input.value = "";
  await post("/api/participant", { name });
});

// ---- Picking: actions --------------------------------------------
$("pickAgainBtn").addEventListener("click", () => {
  if ($("pickAgainBtn").disabled) return;
  const ex = state.selected ? state.selected.id : null;
  post("/api/pick", ex ? { exclude: ex } : {});
});
$("pickCancelBtn").addEventListener("click", () => {
  // Stop any in-flight topic roll synchronously so its settle timer can't fire
  // a late /assign that overrides this cancel before the server roundtrip lands.
  clearTopicRoll();
  post("/api/pick/cancel");
});
$("randomTopicBtn").addEventListener("click", randomizeTopic);

// ---- Focus: done / back ------------------------------------------
$("focusDoneBtn").addEventListener("click", () => {
  const tid = $("focusDoneBtn").dataset.tid;
  if (tid) post(`/api/topic/${tid}/done`);
});
$("focusBackBtn").addEventListener("click", () => {
  const tid = $("focusBackBtn").dataset.tid;
  if (tid) post(`/api/topic/${tid}/reopen`);
});

// ---- Global click delegation (topic cards, roster chips) ---------
const CLICK_ACTIONS = {
  assign: (tid) => tid && post(`/api/topic/${tid}/assign`),
  reopen: (tid) => tid && post(`/api/topic/${tid}/reopen`),
  "remove-topic": (tid) => tid && confirm("Remove this topic?") && post(`/api/topic/${tid}/remove`),
  edit: (tid) => tid && editTopic(tid),
  select: (_tid, pid) => pid && post("/api/select", { pid }),
  "remove-p": (_tid, pid) => pid && post(`/api/participant/${pid}/remove`),
  "open-add": () => openAddEditor(),
};
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  CLICK_ACTIONS[el.dataset.act]?.(el.dataset.tid, el.dataset.pid);
});

// Edit via a small on-brand dialog (native <dialog>: accessible, ESC-to-close,
// and unaffected by the live grid re-render that would wipe an inline form).
let editingTid = null;
function editTopic(tid) {
  const t = state.topics.find((x) => x.id === tid);
  if (!t) return;
  editingTid = tid;
  $("editHl").value = t.headline;
  $("editDt").value = t.details || "";
  const d = $("editDialog");
  if (typeof d.showModal === "function") d.showModal();
  else d.setAttribute("open", "");
  $("editHl").focus();
  $("editHl").select();
}
// Mirror the showModal/open-attr guard used to open: on browsers without native
// <dialog>, .close() is undefined and would throw, locking the UI.
function closeEditDialog() {
  editingTid = null;
  const d = $("editDialog");
  if (typeof d.close === "function") d.close();
  else d.removeAttribute("open");
}
$("editForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const headline = $("editHl").value.trim();
  if (!headline) {
    $("editHl").focus();
    return;
  } // server rejects blank
  const details = $("editDt").value.trim();
  if (editingTid) post(`/api/topic/${editingTid}/edit`, { headline, details });
  closeEditDialog();
});
$("editCancel").addEventListener("click", closeEditDialog);
// Native <dialog> Escape/backdrop close bypasses closeEditDialog(); keep the
// editingTid lifecycle correct no matter how the dialog goes away.
$("editDialog").addEventListener("close", () => {
  editingTid = null;
});

// ---- Keyboard: Escape cancels a pick -----------------------------
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("stage").hidden && state.selected) {
    // Mirror the Cancel button: stop any in-flight topic roll synchronously so
    // its settle timer can't fire a late /assign that overrides this cancel.
    clearTopicRoll();
    post("/api/pick/cancel");
  }
});

// ====================================================================
//  LIVE STREAM
// ====================================================================
function eachEl(ids, fn) {
  for (const id of ids) {
    const el = $(id);
    if (el) fn(el);
  }
}

function setLive(text, stale) {
  eachEl(["live", "live2"], (el) => {
    el.textContent = text;
  });
  eachEl(["liveDot", "liveDot2"], (el) => {
    el.classList.toggle("stale", !!stale);
  });
}

// Server transport: today's exact behavior, just moved behind the interface.
// post() fetches /api/*; subscribe() streams snapshots from the /events SSE.
function serverTransport() {
  return {
    post(url, body) {
      return fetch(url, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    },
    subscribe(onSnapshot) {
      const es = new EventSource("/events");
      es.onmessage = (e) => {
        let snap;
        try {
          snap = JSON.parse(e.data);
        } catch {
          return;
        }
        onSnapshot(snap);
      };
      es.onerror = () => setLive("reconnecting", true);
      es.onopen = () => setLive("live", false);
    },
  };
}

// Local transport: no backend. post() routes the /api/* URL to an engine.js
// method (the same calls board.py makes server-side); subscribe() wires the
// engine's snapshot stream straight into render(). There's no connection to
// drop here, so the status reads "live" once and never goes "reconnecting".
const LOCAL_ROUTES = [
  [/^\/api\/participant$/, (e, _m, b) => e.addParticipant(b.name)],
  [/^\/api\/participant\/([^/]+)\/remove$/, (e, m) => e.removeParticipant(m[1])],
  [/^\/api\/topic$/, (e, _m, b) => e.addTopic(b.headline, b.details)],
  [/^\/api\/topics$/, (e, _m, b) => e.addTopics(b.topics, b.replace)],
  [/^\/api\/topic\/([^/]+)\/edit$/, (e, m, b) => e.editTopic(m[1], b.headline, b.details)],
  [/^\/api\/topic\/([^/]+)\/remove$/, (e, m) => e.removeTopic(m[1])],
  [/^\/api\/topic\/([^/]+)\/done$/, (e, m) => e.markDone(m[1])],
  [/^\/api\/topic\/([^/]+)\/reopen$/, (e, m) => e.reopenTopic(m[1])],
  [/^\/api\/topic\/([^/]+)\/assign$/, (e, m) => e.assign(m[1])],
  [/^\/api\/pick$/, (e, _m, b) => e.pick(b.exclude)],
  [/^\/api\/select$/, (e, _m, b) => e.select(b.pid)],
  [/^\/api\/pick\/cancel$/, (e) => e.cancelPick()],
  [/^\/api\/reset$/, (e) => e.reset()],
  [/^\/api\/demo\/start$/, (e) => e.startDemo()],
  [/^\/api\/demo\/stop$/, (e) => e.stopDemo()],
];

function localTransport(engine) {
  return {
    post(url, body) {
      // Match on the path only; app.js passes bare paths, but be robust to a
      // full URL too. An unknown route is a safe no-op (mirrors board.py's 404).
      const path = new URL(url, "http://x").pathname;
      const b = body || {};
      for (const [re, run] of LOCAL_ROUTES) {
        const m = re.exec(path);
        if (m) {
          run(engine, m, b);
          break;
        }
      }
      return Promise.resolve();
    },
    subscribe(onSnapshot) {
      engine.subscribe(onSnapshot);
      setLive("live", false);
    },
  };
}

// Probe for a backend: GET events and confirm it's an SSE stream. Any failure
// (no server, wrong content-type, timeout) means we're a static page, so fall
// back to standalone. The path is relative so it works from any GitHub Pages
// subpath. We open and immediately cancel the stream we used to probe.
async function hasServer() {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 1500);
  try {
    const res = await fetch("events", { signal: ctrl.signal });
    const ct = res.headers.get("content-type") || "";
    res.body?.cancel?.();
    return res.ok && ct.includes("text/event-stream");
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

// app.js is a module, so top-level await is allowed. The event handlers above
// registered synchronously already; any post() they fire before the probe
// resolves is buffered on transportReady and flushed once we mark it ready.
const engine = createEngine();
activeTransport = (await hasServer()) ? serverTransport() : localTransport(engine);
markTransportReady(activeTransport);
activeTransport.subscribe(render);
