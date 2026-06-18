import { describe, it, expect } from "vitest";
import { parseSseFrame } from "../lib/api";

// /qa/stream SSE 프레임 파서. 초안 생성 진행도를 백엔드 단계와 연계하는 핵심 로직이다.
describe("parseSseFrame", () => {
  it("stage 이벤트(stage/label)를 파싱한다", () => {
    const r = parseSseFrame('event: stage\ndata: {"stage":"retrieving","label":"유사 사례 분석 중"}');
    expect(r).toEqual({ event: "stage", data: { stage: "retrieving", label: "유사 사례 분석 중" } });
  });

  it("done 이벤트의 중첩 응답을 파싱한다", () => {
    const r = parseSseFrame('event: done\ndata: {"success":true,"data":{"answer":"초안 내용"}}');
    expect(r?.event).toBe("done");
    expect((r?.data as { data: { answer: string } }).data.answer).toBe("초안 내용");
  });

  it("event 라인이 없으면 message로 처리한다", () => {
    expect(parseSseFrame('data: {"a":1}')).toEqual({ event: "message", data: { a: 1 } });
  });

  it("data 라인이 없으면 null", () => {
    expect(parseSseFrame("event: stage")).toBeNull();
  });

  it("data JSON이 깨지면 null", () => {
    expect(parseSseFrame("event: stage\ndata: {oops")).toBeNull();
  });
});
