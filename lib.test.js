import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clearStoredTopics,
  eligibleNames,
  escapeHtml,
  fmtTime,
  loadStoredTopics,
  parsePaste,
  saveStoredTopics,
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
  it("returns present, unanswered, non-host names in order", () => {
    const s = {
      participants: [
        { name: "Host", present: true, answered: false, is_host: true },
        { name: "Ann", present: true, answered: false, is_host: false },
        { name: "Bob", present: true, answered: true, is_host: false },
        { name: "Cy", present: false, answered: false, is_host: false },
        { name: "Dee", present: true, answered: false, is_host: false },
      ],
    };
    expect(eligibleNames(s)).toEqual(["Ann", "Dee"]);
  });
  it("excludes the host even when otherwise eligible", () => {
    const s = {
      participants: [{ name: "Host", present: true, answered: false, is_host: true }],
    };
    expect(eligibleNames(s)).toEqual([]);
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

describe("fmtTime", () => {
  it("formats a timestamp as a time string", () => {
    const out = fmtTime(Date.UTC(2026, 0, 1, 15, 30));
    expect(typeof out).toBe("string");
    expect(out).toMatch(/\d/);
  });
});
