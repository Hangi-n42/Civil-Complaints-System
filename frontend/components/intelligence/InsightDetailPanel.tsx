import type { IntelPublicInsightCard } from "@/lib/api";
import { InsightPriorityBadge } from "./InsightPriorityBadge";
import { actionTypeLabel, groupActionsByHorizon, insightStatusLabel, labeledCount } from "./insight";
import { EvidencePackDrawer } from "./EvidencePackDrawer";

// 상세 패널 하단 액션 버튼(§4.3 ⑥). 동작 연결은 차기 — 지금은 자리만.
// (EvidencePack 보기는 아래 EvidencePackDrawer로 실제 제공)
const ACTION_BUTTONS = ["확인 처리", "담당 부서 공유", "조치 계획으로 전환", "기각"];

// 행정 인사이트 상세 패널(핸드오프 §4.3). 우측 슬라이드 패널 + 반투명 배경 클릭/닫기.
export function InsightDetailPanel({
  insight,
  onClose,
  onOpenAlert,
}: {
  insight: IntelPublicInsightCard;
  onClose: () => void;
  onOpenAlert?: (alertId: string) => void;
}) {
  const actionGroups = groupActionsByHorizon(insight.recommended_actions);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" aria-label="닫기" onClick={onClose} className="absolute inset-0 bg-black/30" />

      <div className="relative h-full w-full max-w-xl overflow-y-auto bg-white shadow-xl">
        {/* 1. 헤더: 제목·우선순위·상태·담당부서 후보 */}
        <div className="sticky top-0 border-b border-slate-200 bg-white px-6 py-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">{insight.type_label}</span>
              <InsightPriorityBadge color={insight.color} label={insight.priority_label} />
              <span className="text-[11px] text-slate-400">{insightStatusLabel(insight.status)}</span>
            </div>
            <button type="button" onClick={onClose} aria-label="닫기" className="rounded p-1 text-slate-400 hover:bg-slate-100">
              ✕
            </button>
          </div>
          <h2 className="text-base font-extrabold text-slate-900">{insight.title}</h2>
          {insight.related_department && (
            <p className="mt-1 text-xs text-slate-500">
              담당 부서 후보: <span className="font-semibold text-slate-700">{insight.related_department}</span>
            </p>
          )}
        </div>

        <div className="space-y-6 px-6 py-5">
          {/* 2. 요약 + 핵심 진단 */}
          <section>
            <h3 className="mb-1 text-xs font-bold text-slate-500">요약</h3>
            <p className="text-sm text-slate-700">{insight.summary}</p>
            {insight.problem_diagnosis && (
              <>
                <h3 className="mb-1 mt-3 text-xs font-bold text-slate-500">핵심 진단</h3>
                <p className="text-sm text-slate-700">{insight.problem_diagnosis}</p>
              </>
            )}
          </section>

          {/* 3. 추천 조치 — horizon별 그룹(즉시/단기/중기/장기) */}
          {actionGroups.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-bold text-slate-500">추천 조치</h3>
              <div className="space-y-3">
                {actionGroups.map((group) => (
                  <div key={group.key}>
                    <div className="mb-1 text-[11px] font-bold text-slate-400">{group.label}</div>
                    <div className="space-y-2">
                      {group.actions.map((action, idx) => (
                        <div key={idx} className="rounded-lg border border-slate-200 p-3">
                          <div className="mb-1 flex items-center gap-2">
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-bold text-white">
                              {actionTypeLabel(action.action_type)}
                            </span>
                            <span className="text-sm font-semibold text-slate-800">{action.action}</span>
                          </div>
                          {action.why && <p className="text-xs text-slate-500">{action.why}</p>}
                          {action.responsible_unit_hint && (
                            <p className="mt-0.5 text-[11px] text-slate-400">담당 후보: {action.responsible_unit_hint}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 4. 근거 분석: top_aspects / citizen_requests / 대표 근거 */}
          <section>
            <h3 className="mb-2 text-xs font-bold text-slate-500">근거 분석</h3>
            {insight.top_aspects.length > 0 && (
              <div className="mb-2">
                <div className="mb-1 text-[11px] font-bold text-slate-400">반복 불편 측면</div>
                <ul className="space-y-1">
                  {insight.top_aspects.map((aspect, idx) => {
                    const { label, count } = labeledCount(aspect, "aspect");
                    return (
                      <li key={idx} className="text-xs text-slate-600">
                        · {label} <span className="text-slate-400">({count}건)</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {insight.citizen_requests.length > 0 && (
              <div className="mb-2">
                <div className="mb-1 text-[11px] font-bold text-slate-400">시민 요구</div>
                <ul className="space-y-1">
                  {insight.citizen_requests.map((req, idx) => {
                    const { label, count } = labeledCount(req, "request");
                    return (
                      <li key={idx} className="text-xs text-slate-600">
                        · {label} <span className="text-slate-400">({count}건)</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            <div className="text-[11px] text-slate-400">
              대표 근거 민원 {insight.representative_evidence_ids.length}건 ·{" "}
              {insight.linked_alert_ids.length > 0 && onOpenAlert ? (
                <button
                  type="button"
                  onClick={() => onOpenAlert(insight.linked_alert_ids[0])}
                  className="font-semibold text-blue-600 hover:underline"
                >
                  연결 경보 {insight.linked_alert_ids.length}건
                </button>
              ) : (
                <span>연결 경보 {insight.linked_alert_ids.length}건</span>
              )}
            </div>
          </section>

          {/* 근거 패키지(관리자/디버그) — masked_text만 */}
          <EvidencePackDrawer insightId={insight.id} />

          {/* 5. 불확실성 · 추가 확인 */}
          {insight.uncertainty.length > 0 && (
            <section>
              <h3 className="mb-1 text-xs font-bold text-slate-500">불확실성 · 추가 확인</h3>
              <ul className="space-y-1">
                {insight.uncertainty.map((item, idx) => (
                  <li key={idx} className="text-xs text-slate-600">· {item}</li>
                ))}
              </ul>
            </section>
          )}

          {/* 6. 액션 버튼(자리만 — 동작은 #428) */}
          <section className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
            {ACTION_BUTTONS.map((label) => (
              <button
                key={label}
                type="button"
                disabled
                title="다음 단계에서 연결됩니다"
                className="cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-400"
              >
                {label}
              </button>
            ))}
          </section>
        </div>
      </div>
    </div>
  );
}
