"use client";

import { useState } from "react";
import { fetchEvidencePackApi, type IntelEvidencePack } from "@/lib/api";

// 인사이트 근거 패키지(관리자/디버그). 핸드오프 §5: masked_text만 노출, PII 원문 없음.
// 기본 접힘 — "근거 보기"를 눌러야 펼쳐지고 그때 한 번 fetch한다.
export function EvidencePackDrawer({ insightId }: { insightId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [pack, setPack] = useState<IntelEvidencePack | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !loaded) {
      setLoading(true);
      const res = await fetchEvidencePackApi(insightId);
      setPack(res.data);
      setError(res.error ? res.error.message : null);
      setLoading(false);
      setLoaded(true);
    }
  }

  const complaints = pack?.representative_complaints ?? [];

  return (
    <section className="border-t border-slate-200 pt-4">
      <button type="button" onClick={toggle} className="text-xs font-bold text-slate-500 hover:text-slate-800">
        {open ? "▾" : "▸"} 근거 보기 <span className="font-normal text-slate-400">(관리자/디버그 · 마스킹된 원문)</span>
      </button>

      {open && (
        <div className="mt-2">
          {loading ? (
            <div className="text-xs text-slate-400">근거 패키지를 불러오는 중...</div>
          ) : error ? (
            <div className="text-xs text-red-600">근거 패키지를 불러오지 못했습니다. ({error})</div>
          ) : complaints.length === 0 ? (
            <div className="text-xs text-slate-400">표시할 근거 민원이 없습니다.</div>
          ) : (
            <ul className="space-y-2">
              {complaints.map((complaint, idx) => (
                <li key={idx} className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                  <p className="whitespace-pre-wrap">{complaint.masked_text ?? ""}</p>
                  {(complaint.region || complaint.department) && (
                    <div className="mt-1 text-[11px] text-slate-400">
                      {[complaint.region, complaint.department].filter(Boolean).join(" · ")}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
