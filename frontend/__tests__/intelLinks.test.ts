import { describe, it, expect } from "vitest";
import { findById, resolveLinked } from "../components/intelligence/links";

describe("findById", () => {
  it("id로 항목을 찾는다", () => {
    expect(findById([{ id: "a" }, { id: "b" }], "b")).toEqual({ id: "b" });
  });

  it("없으면 undefined", () => {
    expect(findById([{ id: "a" }], "z")).toBeUndefined();
  });
});

describe("resolveLinked", () => {
  it("linked id를 항목으로 해석(순서 유지)", () => {
    const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
    expect(resolveLinked(["c", "a"], items)).toEqual([{ id: "c" }, { id: "a" }]);
  });

  it("존재하지 않는 id는 제외", () => {
    expect(resolveLinked(["a", "x"], [{ id: "a" }])).toEqual([{ id: "a" }]);
  });

  it("빈 입력은 빈 배열", () => {
    expect(resolveLinked([], [{ id: "a" }])).toEqual([]);
  });
});
