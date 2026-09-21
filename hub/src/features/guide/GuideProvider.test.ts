import { describe, expect, it } from "vitest";
import { coerceStored } from "./GuideProvider";

/** What an earlier build, a hand edit or a corrupted store may leave under `hub.guide.<id>`: none of it may take the page down. */
describe("the guide's stored record is coerced field by field", () => {
  const empty = { persona: undefined, visited: [], ticked: [], dismissed: [], asked: 0, toursDone: [] };

  it("takes a well-formed record as it is", () => {
    expect(coerceStored({ persona: "decide", visited: ["/discover"], ticked: ["a"], dismissed: ["w"], asked: 3, toursDone: ["build"] })).toEqual({
      persona: "decide",
      visited: ["/discover"],
      ticked: ["a"],
      dismissed: ["w"],
      asked: 3,
      toursDone: ["build"],
    });
  });

  it("replaces a null array with an empty one", () => {
    expect(coerceStored({ visited: null })).toEqual(empty);
  });

  it("replaces a number where an array belongs, and drops non-string entries", () => {
    expect(coerceStored({ dismissed: 5 })).toEqual(empty);
    expect(coerceStored({ ticked: "x", dismissed: 5 })).toEqual(empty);
    expect(coerceStored({ visited: ["/a", 3, null, "/b"] }).visited).toEqual(["/a", "/b"]);
  });

  it("falls back for a record that is not an object at all", () => {
    expect(coerceStored([1, 2])).toEqual(empty);
    expect(coerceStored("str")).toEqual(empty);
    expect(coerceStored(null)).toEqual(empty);
    expect(coerceStored(undefined)).toEqual(empty);
  });

  it("keeps only a persona from the known set and a finite non-negative count", () => {
    expect(coerceStored({ persona: "admin" }).persona).toBeUndefined();
    expect(coerceStored({ persona: "use" }).persona).toBe("use");
    expect(coerceStored({ asked: "3" }).asked).toBe(0);
    expect(coerceStored({ asked: -2 }).asked).toBe(0);
    expect(coerceStored({ asked: Number.NaN }).asked).toBe(0);
    expect(coerceStored({ asked: 2.7 }).asked).toBe(2);
  });
});
