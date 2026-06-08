"""B2 — 안전 오버라이드 규칙 (생명·신체 위협 탐지, 재현율 우선).

LLM 비의존·결정적. 생명/신체 위협이 '잠재적으로라도' 있으면 safety_flag=1.
놓치는 것이 최악이라 정밀도보다 재현율을 우선한다(과경보 허용).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# 생명·신체 위협 신호(부산 민원 빈출 포함). 재현율 우선 → 넓게.
_SAFETY_PATTERNS: List[str] = [
    r"가스\s*(?:누출|냄새|샘)", r"폭발", r"붕괴", r"무너", r"침수", r"산사태", r"낙석",
    r"화재", r"불(?:이|길)?\s*나", r"불\s*남", r"연기", r"감전", r"누전", r"고압",
    r"추락", r"떨어(?:져|질|진)", r"낙상", r"넘어(?:져|짐|질|지)", r"미끄(?:러|럽|럼)",
    r"부상", r"다(?:쳐|쳤|치|칠)", r"중상", r"골절", r"피\s*가\s*나", r"출혈",
    r"사고", r"위험", r"위협", r"질식", r"중독", r"식중독", r"익사", r"빠(?:져|질|지)",
    r"실종", r"자살", r"극단적\s*선택", r"죽(?:을|겠|고\s*싶)", r"생명", r"응급",
    r"쓰러", r"의식\s*(?:없|잃)", r"호흡곤란", r"맹견", r"물(?:려|림|렸)", r"개\s*물",
    r"흉기", r"칼\s*들", r"협박", r"폭행", r"추돌", r"충돌", r"전복",
    r"감염", r"전염", r"누수.*전기", r"침하", r"균열",
    r"싱크홀", r"훼손", r"파임", r"먼지", r"분진", r"호흡", r"기침", r"아찔",
    r"피난", r"탄\s*냄새", r"압사", r"깔(?:려|림|릴)", r"전도",
]
_SAFETY_RE = [re.compile(p) for p in _SAFETY_PATTERNS]

# 부정 문맥(키워드가 부정되면 제외). 재현율 보호 위해 명확한 것만.
_NEGATION_RE = re.compile(
    r"위험(?:하지|하진|성은|은|이|도)?\s*않|안전합니다|안전해|위험\s*없|"
    r"사고\s*(?:는|가)?\s*없|다치지\s*않|문제\s*없"
)


def detect_safety(text: str) -> Dict[str, Any]:
    """생명·신체 위협 탐지.

    Returns {"safety_flag": 0|1, "matched": [...], "score": int, "evidence": [...]}.
    """
    text = text or ""
    matched: List[str] = []
    for rx in _SAFETY_RE:
        m = rx.search(text)
        if not m:
            continue
        span = m.group(0)
        # 부정 문맥 회피: 매칭 직후 12자 안에 부정 표현이 있으면 스킵
        tail = text[m.end(): m.end() + 14]
        if _NEGATION_RE.search(span + tail):
            continue
        matched.append(span)

    matched = list(dict.fromkeys(matched))
    flag = 1 if matched else 0
    return {"safety_flag": flag, "matched": matched, "score": len(matched),
            "evidence": matched[:3]}
