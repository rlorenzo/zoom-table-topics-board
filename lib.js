// Pure, DOM-free helpers shared by the UI (app.js) and the unit tests.
// Nothing here touches the live DOM or runs on import, so it's safe to import
// directly in Node/jsdom — that's what makes it unit-testable in isolation.

// ---- formatters --------------------------------------------------
export const fmtTime = (ts) =>
  new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

// ---- paste parsing -----------------------------------------------
// One topic per line; the first "|" splits "headline | details". Blank lines
// and entries with no headline are dropped.
export function parsePaste(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const i = line.indexOf("|");
      if (i === -1) return { headline: line, details: "" };
      return {
        headline: line.slice(0, i).trim(),
        details: line.slice(i + 1).trim(),
      };
    })
    .filter((t) => t.headline);
}

// ---- pick eligibility --------------------------------------------
// The random roll's candidate names: present, not yet answered, and never the
// host. Mirrors the server-side pool.
export function eligibleNames(s) {
  return s.participants.filter((p) => p.present && !p.answered && !p.is_host).map((p) => p.name);
}

// ---- localStorage: the host's topic set (no server persistence) --
const LS_KEY = "tabletopics.topics.v1";

export function loadStoredTopics() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr
      .map((t) => ({
        headline: String(t?.headline || "").trim(),
        details: String(t?.details || "").trim(),
      }))
      .filter((t) => t.headline);
  } catch {
    return [];
  }
}

export function saveStoredTopics(topics) {
  try {
    const slim = topics.map((t) => ({ headline: t.headline, details: t.details || "" }));
    localStorage.setItem(LS_KEY, JSON.stringify(slim));
  } catch {
    /* private mode / quota — non-fatal */
  }
}

export function clearStoredTopics() {
  try {
    localStorage.removeItem(LS_KEY);
  } catch {
    /* ignore */
  }
}

// ---- view / board decision logic ---------------------------------
// Which top-level view a snapshot maps to: focus > picking > board.
export function nextView(s) {
  if (s.activeTopicId) return "focus";
  if (s.selected) return "picking";
  return "board";
}

// The id of the single topic that flipped to "done" between two snapshots, so
// the board can play a one-shot celebration. null if zero or more than one did.
export function newlyDoneId(prevTopics, topics) {
  const wasDone = new Set((prevTopics || []).filter((t) => t.status === "done").map((t) => t.id));
  const nowDone = topics.filter((t) => t.status === "done" && !wasDone.has(t.id));
  return nowDone.length === 1 ? nowDone[0].id : null;
}

// The pick-button hint: distinguishes "round finished" from "room still empty"
// rather than keying off whether topics exist.
export function pickHint({ toGo, answered, hasOpen }) {
  if (toGo === 0 && answered > 0) return "Everyone has had a topic.";
  if (toGo === 0) return "Add people to the room first.";
  if (!hasOpen) return "Add an open topic to pick.";
  return "";
}

// The "N open · M done" topics subhead (empty until there are topics).
export function topicAux({ tTotal, openCount, tDone }) {
  return tTotal ? `${openCount} open · ${tDone} done` : "";
}

// ---- class-list builders -----------------------------------------
export function cardClass(status, choose, lockedOut) {
  return ["card", status, choose ? "choose" : "", lockedOut ? "locked-out" : ""]
    .filter(Boolean)
    .join(" ");
}

export function chipClass(p) {
  return ["chip", p.answered ? "answered" : "", p.present ? "" : "left"].filter(Boolean).join(" ");
}
