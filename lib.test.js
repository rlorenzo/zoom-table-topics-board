import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  cardClass,
  chipClass,
  clearStoredTopics,
  eligibleNames,
  escapeHtml,
  fmtTime,
  initials,
  isConcealed,
  loadConceal,
  loadOnboarded,
  loadStoredTopics,
  newlyDoneId,
  nextView,
  parsePaste,
  pickHint,
  saveConceal,
  saveOnboarded,
  saveStoredTopics,
  showWelcome,
  topicAux,
} from "./lib.js";

const LS_KEY = "tabletopics.topics.v1";

describe("escapeHtml", () => {
  it("escapes the five HTML-significant characters", () => {
    expect(escapeHtml(`<a href="x" data-y='z'>&</a>`)).toBe(
      "&lt;a href=&quot;x&quot; data-y=&#39;z&#39;&gt;&amp;&lt;/a&gt;",
    );
  });
  it("leaves a plain string untouched", () => {
    expect(escapeHtml("Tell us about your week")).toBe("Tell us about your week");
  });
  it("coerces non-strings before escaping", () => {
    expect(escapeHtml(42)).toBe("42");
  });
});

describe("parsePaste", () => {
  it("treats each non-empty line as a headline", () => {
    expect(parsePaste("First\nSecond")).toEqual([
      { headline: "First", details: "" },
      { headline: "Second", details: "" },
    ]);
  });
  it("splits on the first pipe only", () => {
    expect(parsePaste("Topic | a | b")).toEqual([{ headline: "Topic", details: "a | b" }]);
  });
  it("trims whitespace and drops blank lines", () => {
    expect(parsePaste("  A  \n\n   \n B | d ")).toEqual([
      { headline: "A", details: "" },
      { headline: "B", details: "d" },
    ]);
  });
  it("drops entries with no headline (leading pipe)", () => {
    expect(parsePaste("| just details")).toEqual([]);
  });
  it("returns [] for empty input", () => {
    expect(parsePaste("")).toEqual([]);
  });
});

describe("eligibleNames", () => {
  it("returns present, unanswered names in order, host included", () => {
    const s = {
      participants: [
        { name: "Host", present: true, answered: false, is_host: true },
        { name: "Ann", present: true, answered: false, is_host: false },
        { name: "Bob", present: true, answered: true, is_host: false },
        { name: "Cy", present: false, answered: false, is_host: false },
        { name: "Dee", present: true, answered: false, is_host: false },
      ],
    };
    expect(eligibleNames(s)).toEqual(["Host", "Ann", "Dee"]);
  });
  it("includes the host (a full participant)", () => {
    const s = {
      participants: [{ name: "Host", present: true, answered: false, is_host: true }],
    };
    expect(eligibleNames(s)).toEqual(["Host"]);
  });
  it("excludes opted-out (excluded) people", () => {
    const s = {
      participants: [
        { name: "Ann", present: true, answered: false, is_host: false, excluded: true },
        { name: "Bob", present: true, answered: false, is_host: false, excluded: false },
      ],
    };
    expect(eligibleNames(s)).toEqual(["Bob"]);
  });
});

describe("topic localStorage", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("returns [] when nothing is stored", () => {
    expect(loadStoredTopics()).toEqual([]);
  });

  it("round-trips a saved set, slimmed to headline/details", () => {
    saveStoredTopics([{ headline: "A", details: "d", status: "open", id: "x" }, { headline: "B" }]);
    expect(loadStoredTopics()).toEqual([
      { headline: "A", details: "d" },
      { headline: "B", details: "" },
    ]);
  });

  it("trims and drops entries without a headline", () => {
    localStorage.setItem(
      LS_KEY,
      JSON.stringify([{ headline: "  Keep  ", details: " yes " }, { headline: "   " }, {}]),
    );
    expect(loadStoredTopics()).toEqual([{ headline: "Keep", details: "yes" }]);
  });

  it("returns [] for malformed JSON", () => {
    localStorage.setItem(LS_KEY, "{not json");
    expect(loadStoredTopics()).toEqual([]);
  });

  it("returns [] when the stored value is not an array", () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ headline: "x" }));
    expect(loadStoredTopics()).toEqual([]);
  });

  it("clearStoredTopics removes the stored set", () => {
    saveStoredTopics([{ headline: "A", details: "" }]);
    clearStoredTopics();
    expect(loadStoredTopics()).toEqual([]);
  });
});

describe("onboarded flag", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("is false until set", () => {
    expect(loadOnboarded()).toBe(false);
  });

  it("reads true after saveOnboarded", () => {
    saveOnboarded();
    expect(loadOnboarded()).toBe(true);
  });
});

describe("conceal flag", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("is false until set", () => {
    expect(loadConceal()).toBe(false);
  });
  it("round-trips on then off", () => {
    saveConceal(true);
    expect(loadConceal()).toBe(true);
    saveConceal(false);
    expect(loadConceal()).toBe(false);
  });
});

describe("isConcealed", () => {
  it("masks an open topic only while surprise mode is on", () => {
    expect(isConcealed("open", true)).toBe(true);
    expect(isConcealed("open", false)).toBe(false);
  });
  it("never masks a picked topic, even in surprise mode", () => {
    expect(isConcealed("active", true)).toBe(false);
    expect(isConcealed("done", true)).toBe(false);
  });
});

describe("showWelcome", () => {
  const cold = { demo: false, topics: [], participants: [] };

  it("shows on a cold start when not onboarded", () => {
    expect(showWelcome(cold, false)).toBe(true);
  });
  it("hides once onboarded", () => {
    expect(showWelcome(cold, true)).toBe(false);
  });
  it("hides while a demo is running", () => {
    expect(showWelcome({ ...cold, demo: true }, false)).toBe(false);
  });
  it("hides when topics already exist", () => {
    expect(showWelcome({ ...cold, topics: [{ id: "t1" }] }, false)).toBe(false);
  });
  it("hides when someone is already in the room", () => {
    expect(showWelcome({ ...cold, participants: [{ id: "p1" }] }, false)).toBe(false);
  });
});

describe("initials", () => {
  it("takes the first and last word initials", () => {
    expect(initials("Diego Santos")).toBe("DS");
  });
  it("uses one letter for a single name", () => {
    expect(initials("Maya")).toBe("M");
  });
  it("ignores middle words", () => {
    expect(initials("Ana Maria Lopez")).toBe("AL");
  });
  it("uppercases", () => {
    expect(initials("priya patel")).toBe("PP");
  });
  it("skips leading punctuation/emoji to the first real character", () => {
    expect(initials("🎤 Sam")).toBe("S");
  });
  it("falls back to a dot for an empty name", () => {
    expect(initials("   ")).toBe("·");
    expect(initials("")).toBe("·");
  });
});

describe("fmtTime", () => {
  it("formats a timestamp as a time string", () => {
    const out = fmtTime(Date.UTC(2026, 0, 1, 15, 30));
    expect(typeof out).toBe("string");
    expect(out).toMatch(/\d/);
  });
});

describe("nextView", () => {
  it("prioritises focus > picking > board", () => {
    expect(nextView({ activeTopicId: "t", selected: { id: "p" } })).toBe("focus");
    expect(nextView({ activeTopicId: null, selected: { id: "p" } })).toBe("picking");
    expect(nextView({ activeTopicId: null, selected: null })).toBe("board");
  });
});

describe("newlyDoneId", () => {
  const open = (id) => ({ id, status: "open" });
  const done = (id) => ({ id, status: "done" });
  it("returns the id of the one topic that just became done", () => {
    expect(newlyDoneId([open("a")], [done("a")])).toBe("a");
  });
  it("returns null when nothing newly completed", () => {
    expect(newlyDoneId([done("a")], [done("a")])).toBeNull();
  });
  it("returns null when more than one completed at once", () => {
    expect(newlyDoneId([open("a"), open("b")], [done("a"), done("b")])).toBeNull();
  });
  it("tolerates a missing previous list", () => {
    expect(newlyDoneId(undefined, [done("a")])).toBe("a");
  });
});

describe("pickHint", () => {
  it("says everyone went when the pool is empty but someone answered", () => {
    expect(pickHint({ toGo: 0, answered: 3, hasOpen: true })).toBe("Everyone has had a topic.");
  });
  it("asks for people when the room is empty", () => {
    expect(pickHint({ toGo: 0, answered: 0, hasOpen: true })).toBe("Add people to the room first.");
  });
  it("asks for a topic when none are open", () => {
    expect(pickHint({ toGo: 2, answered: 0, hasOpen: false })).toBe("Add an open topic to pick.");
  });
  it("is empty when a pick is possible", () => {
    expect(pickHint({ toGo: 2, answered: 0, hasOpen: true })).toBe("");
  });
});

describe("topicAux", () => {
  it("summarises open/done counts", () => {
    expect(topicAux({ tTotal: 5, openCount: 3, tDone: 2 })).toBe("3 open · 2 done");
  });
  it("is empty with no topics", () => {
    expect(topicAux({ tTotal: 0, openCount: 0, tDone: 0 })).toBe("");
  });
});

describe("cardClass / chipClass", () => {
  it("builds a card class, dropping empty parts", () => {
    expect(cardClass("open", false, false)).toBe("card open");
    expect(cardClass("open", true, false)).toBe("card open choose");
    expect(cardClass("done", false, true)).toBe("card done locked-out");
  });
  it("builds a chip class from participant flags", () => {
    expect(chipClass({ answered: true, present: true })).toBe("chip answered");
    expect(chipClass({ answered: false, present: false })).toBe("chip left");
    expect(chipClass({ answered: false, present: true })).toBe("chip");
    expect(chipClass({ answered: false, present: true, excluded: true })).toBe("chip excluded");
  });
});
