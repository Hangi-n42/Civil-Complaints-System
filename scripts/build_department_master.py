"""배정용 마스터 부서 데이터 생성 (responsible_unit 도출 1단계).

입력: busan_departments_tasks.json  (부서 150개, 업무 3,368개)
출력:
  - busan_departments_master.json  : 배정 대상 부서/업무만 남긴 정제본
  - busan_departments_master.stats.json : 필터링 통계(검토용)

필터 전략 (2-layer + leaf 우선):
  Layer A. 부서 블랙리스트
     - 시민 민원과 무관한 내부 지원·보좌·감사·기획예산·살림 부서를 제외.
  Layer B. 업무(task) 단위 보일러플레이트 제거  ★ 핵심
     - 거의 모든 부서에 반복 등장하는 내부 행정 업무를 제거해 검색 신호를 선명하게.
  Layer C. leaf 우선
     - 정제 후 실질 업무가 MIN_TASKS 미만으로 남는 부서(순수 국/실 롤업,
       직책 placeholder)는 배정 대상에서 제외한다.

주의: 이 단계는 결정적(deterministic)이며 모델/네트워크 불필요.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "departments" / "busan_departments_tasks.json"
OUT = ROOT / "data" / "departments" / "busan_departments_master.json"
STATS = ROOT / "data" / "departments" / "busan_departments_master.stats.json"

# 정제 후 부서에 최소 이만큼의 실질 업무가 남아야 배정 대상으로 유지한다.
MIN_TASKS = 2

# ── Layer A: 부서 블랙리스트 (정확한 부서명) ──────────────────────────────
DEPARTMENT_BLACKLIST = {
    # 시장/부시장 직책 placeholder 및 보좌·홍보
    "행정부시장", "미래혁신부시장", "소방재난본부장",
    "대변인", "홍보담당관", "공보담당관",
    # 자치경찰위원회 내부 행정
    "자치경찰위원회", "사무국", "자치경찰행정과", "자치경찰관리과",
    # 감사·청렴
    "감사위원회", "감사담당관", "청렴담당관",
    # 기획조정실 내부 기획/예산/법무/세정/회계
    "기획조정실", "기획관", "기획담당관", "조직담당관", "법무담당관",
    "예산담당관", "공공기관담당관", "재정협력담당관",
    "세정정책담당관", "세정운영담당관", "회계재산담당관",
    # 행정자치국 내부 살림/정보화
    "행정자치국", "자치행정과", "총무과", "인사과", "정보화정책과",
    # 소방 내부 행정/감사/회계
    "소방행정과", "소방감사담당관", "회계장비담당관",
}

# ── Layer B: 업무 단위 보일러플레이트 패턴 ────────────────────────────────
# 부서 도메인과 무관한 내부 행정 반복 업무. 검색 노이즈의 핵심.
# anchored 처리: 복지 '급여/수당' 등 도메인어가 오제거되지 않도록 한정.
_BOILERPLATE_RAW = [
    r"업무\s*총괄",
    r"총괄$",
    r"주요\s*업무계획",
    r"업무보고",
    r"조직\s*및\s*인사",
    r"인사에\s*관한",
    r"당면지시",
    r"현안\)?사항\s*처리",
    r"구상사업",
    r"성과관리",
    r"BSC",
    r"국정감사",
    r"법제심사",
    r"법령[·\s]*조례",
    r"서무",
    r"보안",
    r"청렴",
    r"기록물",
    r"회계\(지출\)",
    r"지출.*물품",
    r"물품\s*(?:및\s*)?업무추진비",
    r"업무추진비",
    r"청사\s*관리",
    r"예산\s*결산",
    r"예산\s*편성",
    r"수행비서",
    r"기타\s*타?\s*직원에\s*속하지\s*않는",
    r"표창",
    r"공적심의",
    r"간부회의",
    r"회의지원",
    r"시의회에\s*관한",
    r"행정사무감사",
    r"건의자료",
    r"중앙부처\s*건의",
    # 국/실 롤업 항목에 섞인 내부 행정 (anchored)
    r"국급여",
    r"연말정산",
    r"각종\s*수당",
    r"국장\s*일정",
    r"국장\s*운전",
    r"차량\s*유지관리",
    r"국회\s*및\s*시의회",
    r"포상\s*및\s*공적",
    r"공적\s*심사",
    r"회의\s*홍보",
]
BOILERPLATE_PATTERNS: List[re.Pattern] = [re.compile(p) for p in _BOILERPLATE_RAW]

# ── soft 패턴: '총괄/성과관리/업무보고' 등 일반 롤업. 도메인 업무에도 흔히 붙어
#    오제거를 일으키므로, 도메인 앵커가 있으면 이 사유만으로는 제거하지 않는다.
#    (하드 패턴: 업무추진비/청사관리/회계 등은 도메인 여부와 무관하게 항상 제거)
_SOFT_RAW = {
    r"업무\s*총괄", r"총괄$", r"주요\s*업무계획", r"업무보고", r"성과관리", r"BSC",
}
_SOFT_PATTERNS = {
    pat for raw, pat in zip(_BOILERPLATE_RAW, BOILERPLATE_PATTERNS) if raw in _SOFT_RAW
}

# 시민 대면 규제/서비스 도메인 앵커. 이 단어가 있으면 실제 소관 업무로 보고
# soft 보일러플레이트(총괄 등) 사유로 제거하지 않는다.
_DOMAIN_ANCHOR = re.compile(
    "건설기계|지게차|건축|주택|도로|교통|상수도|하수도|상하수도|수도|환경|폐기물|"
    "위생|식품|동물|축산|도시계획|공원|녹지|하천|면허|허가|등록|인허가|보건|의료|"
    "복지|아동|노인|장애|청소년|자동차|차량|소방|재난|농업|수산|어업|산림|관광|"
    "문화재|위험물|대기|수질|토지|측량"
)


def is_boilerplate(task: str) -> bool:
    t = task.strip()
    matched = [p for p in BOILERPLATE_PATTERNS if p.search(t)]
    if not matched:
        return False
    # 도메인 업무가 soft 사유로만 걸리면 보존(예: "건설기계 위임 사무 총괄").
    if _DOMAIN_ANCHOR.search(t) and all(p in _SOFT_PATTERNS for p in matched):
        return False
    return True


def clean_tasks(tasks: List[str]) -> List[str]:
    seen = set()
    kept: List[str] = []
    for raw in tasks:
        t = " ".join(str(raw).split())
        if not t or is_boilerplate(t):
            continue
        if t in seen:
            continue
        seen.add(t)
        kept.append(t)
    return kept


def build_master(src: List[Dict]) -> tuple[List[Dict], Dict]:
    """순수 함수: 원본 → (master, stats). 테스트에서 직접 호출 가능."""
    master: List[Dict] = []
    dropped_dept: List[Dict] = []
    boilerplate_removed = 0
    total_src_tasks = 0

    for dept in src:
        name = dept["department"]
        tasks = dept.get("tasks", [])
        total_src_tasks += len(tasks)

        if name in DEPARTMENT_BLACKLIST:
            dropped_dept.append({"department": name, "reason": "blacklist",
                                 "src_tasks": len(tasks)})
            continue

        cleaned = clean_tasks(tasks)
        boilerplate_removed += (len(tasks) - len(cleaned))

        if len(cleaned) < MIN_TASKS:
            dropped_dept.append({"department": name, "reason": "too_few_after_clean",
                                 "src_tasks": len(tasks), "cleaned_tasks": len(cleaned)})
            continue

        master.append({"department": name, "url": dept.get("url", ""), "tasks": cleaned})

    stats = {
        "source_departments": len(src),
        "source_tasks": total_src_tasks,
        "master_departments": len(master),
        "master_tasks": sum(len(d["tasks"]) for d in master),
        "dropped_departments": len(dropped_dept),
        "boilerplate_tasks_removed": boilerplate_removed,
        "min_tasks_threshold": MIN_TASKS,
        "dropped_detail": dropped_dept,
        "kept_departments": [d["department"] for d in master],
    }
    return master, stats


def main() -> None:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    master, stats = build_master(src)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"source:  {stats['source_departments']} depts / {stats['source_tasks']} tasks")
    print(f"master:  {stats['master_departments']} depts / {stats['master_tasks']} tasks")
    print(f"dropped: {stats['dropped_departments']} depts ; "
          f"boilerplate removed: {stats['boilerplate_tasks_removed']} tasks")
    print(f"-> {OUT}, {STATS}")


if __name__ == "__main__":
    main()
