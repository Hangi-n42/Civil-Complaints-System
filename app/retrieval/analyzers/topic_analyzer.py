from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TopicType = Literal["welfare", "traffic", "environment", "construction", "general"]

# top-1과 top-2 원점수 차이가 top-1의 이 비율 이하이면 ambiguous 처리
CONFIDENCE_AMBIGUITY_MARGIN = 0.15

# 전체 점수 합 대비 top-1 비율이 이 값 미만이면 "general"로 강등
CONFIDENCE_MIN_THRESHOLD = 0.40

# 기관명 등 false-positive 유발 패턴 (매칭 전 제거)
_NEGATIVE_PATTERNS: tuple[str, ...] = (
    "환경부",
    "환경공단",
    "환경청",
    "교통공단",
    "교통안전공단",
    "교통안전",
    "교통방송",
    "건설교통부",
    "국토교통부",
    "안전처",
    "재난안전",
    "안전관리",
    "안전교육",
    "안전벨트",
    "안전모",
    "안전장비",
    "안전수칙",
    "안전점검",
    "복지부",
    "보건복지부",
)

# (keyword, weight) — 키워드 고유성·분별력이 높을수록 가중치 높임
_DEFAULT_KEYWORD_MAP: dict[str, list[tuple[str, float]]] = {
    "welfare": [
        # 급여/수급
        ("기초생활", 1.5),
        ("수급", 1.3),
        ("생계급여", 1.5),
        ("의료급여", 1.4),
        ("주거급여", 1.4),
        ("교육급여", 1.4),
        ("차상위", 1.3),
        ("저소득", 1.2),
        ("기초연금", 1.4),
        ("급여", 1.2),
        ("긴급복지", 1.5),
        ("복지급여", 1.5),
        ("생계비", 1.3),
        ("생활비지원", 1.4),
        # 주거
        ("임대주택", 1.3),
        ("공공임대", 1.4),
        ("영구임대", 1.4),
        ("전세임대", 1.4),
        ("국민임대", 1.4),
        ("행복주택", 1.3),
        ("사회주택", 1.3),
        ("주거복지", 1.4),
        # 지원금/보조금
        ("보조금", 1.1),
        ("지원금", 1.0),
        ("난방비", 1.1),
        ("의료비지원", 1.3),
        ("복지카드", 1.3),
        ("아동수당", 1.4),
        ("양육수당", 1.4),
        ("육아휴직", 1.2),
        ("출산지원", 1.2),
        ("다자녀", 1.2),
        # 대상별
        ("복지", 1.0),
        ("노인", 1.0),
        ("장애인", 1.2),
        ("장애등급", 1.4),
        ("아동", 0.9),
        ("청소년", 0.9),
        ("한부모", 1.3),
        ("다문화", 1.1),
        ("독거노인", 1.4),
        ("취약계층", 1.3),
        ("사회적약자", 1.3),
        # 서비스/기관
        ("돌봄", 1.1),
        ("요양", 1.2),
        ("방문요양", 1.3),
        ("재가서비스", 1.3),
        ("자활", 1.1),
        ("사례관리", 1.3),
        ("복지관", 1.2),
    ],
    "traffic": [
        # 도로 인프라
        ("도로", 0.9),
        ("노면", 1.1),
        ("포트홀", 1.5),
        ("도로파손", 1.4),
        ("도로침하", 1.4),
        ("차선", 1.1),
        ("교차로", 1.1),
        ("도로표지판", 1.3),
        ("방호울타리", 1.3),
        ("노면표시", 1.2),
        ("갓길", 1.2),
        # 주차/통행
        ("교통", 0.9),
        ("주차", 1.0),
        ("불법주정차", 1.5),
        ("주차장", 1.1),
        ("주정차", 1.3),
        ("평행주차", 1.3),
        ("주차시설", 1.2),
        ("주차수급", 1.3),
        ("견인", 1.3),
        ("불법유턴", 1.4),
        ("통행", 0.8),
        ("일방통행", 1.3),
        ("주차단속", 1.4),
        ("노상주차", 1.3),
        # 신호/안전시설
        ("신호", 1.1),
        ("신호등", 1.3),
        ("횡단보도", 1.3),
        ("가로등", 1.2),
        ("과속", 1.2),
        ("속도위반", 1.3),
        ("스쿨존", 1.4),
        ("어린이보호구역", 1.4),
        ("교통사고", 1.3),
        ("안전표지", 1.2),
        ("무단횡단", 1.2),
        # 대중교통
        ("버스노선", 1.4),
        ("버스", 0.9),
        ("버스정류장", 1.2),
        ("지하철", 0.9),
        ("택시", 0.9),
        ("대중교통", 1.1),
        # 이동수단
        ("자전거도로", 1.3),
        ("자전거", 0.9),
        ("킥보드", 1.1),
        ("오토바이", 1.0),
        ("이륜차", 1.1),
        ("개인형이동장치", 1.3),
        # 기타
        ("보행자", 0.9),
        ("차량", 0.8),
        ("교통민원", 1.1),
        ("주택가교통", 1.2),
    ],
    "environment": [
        # 소음/진동
        ("소음", 1.2),
        ("진동", 1.1),
        ("층간소음", 1.5),
        ("공사소음", 1.4),
        ("소음측정", 1.3),
        ("소음민원", 1.4),
        # 악취/대기
        ("악취", 1.4),
        ("미세먼지", 1.5),
        ("매연", 1.3),
        ("분진", 1.3),
        ("대기오염", 1.4),
        ("황사", 1.1),
        ("냄새", 1.1),
        ("음식점악취", 1.4),
        ("축사악취", 1.4),
        ("연기", 1.0),
        # 폐기물/청소
        ("폐기물", 1.4),
        ("쓰레기", 1.1),
        ("재활용", 0.9),
        ("네프론", 1.4),
        ("페트병", 1.1),
        ("캔", 0.9),
        ("생활폐기물", 1.4),
        ("불법투기", 1.4),
        ("음식물쓰레기", 1.3),
        ("대형폐기물", 1.3),
        ("쓰레기무단투기", 1.5),
        ("방치폐기물", 1.4),
        ("쓰레기봉투", 1.2),
        ("분리수거", 1.1),
        ("폐기물처리", 1.4),
        # 수질/하수
        ("폐수", 1.5),
        ("수질", 1.3),
        ("하수", 1.1),
        ("하수도", 1.2),
        ("오수", 1.3),
        ("수질오염", 1.4),
        ("강하천", 1.0),
        ("하천오염", 1.4),
        # 해충/방역
        ("방역", 1.0),
        ("해충", 1.1),
        ("쥐", 1.0),
        ("모기", 1.0),
        ("벌레", 0.9),
        ("빈대", 1.2),
        ("바퀴벌레", 1.2),
        ("방제", 1.1),
        # 토양/기타
        ("토양오염", 1.5),
        ("환경", 0.8),
        ("오염", 1.0),
        ("침수", 1.1),
        ("녹조", 1.3),
        ("환경오염", 1.3),
    ],
    "construction": [
        # 건축 인허가
        ("건축", 1.1),
        ("건축허가", 1.4),
        ("건축신고", 1.3),
        ("건축물", 1.0),
        ("용도변경", 1.4),
        ("인허가", 1.4),
        ("착공", 1.4),
        ("준공", 1.4),
        ("사용승인", 1.4),
        ("건축심의", 1.4),
        ("불법건축물", 1.5),
        ("무허가건축", 1.5),
        ("일조권", 1.5),
        # 공사 현장
        ("공사", 1.1),
        ("토목", 1.3),
        ("공사현장", 1.3),
        ("건설현장", 1.3),
        ("지하공사", 1.4),
        ("도로공사", 1.3),
        ("굴착", 1.4),
        ("터파기", 1.5),
        ("비계", 1.5),
        ("철거", 1.4),
        ("발파", 1.5),
        ("콘크리트", 1.1),
        ("굴삭기", 1.3),
        # 시설/보수
        ("시설", 0.7),
        ("보수", 1.0),
        ("시설물", 1.1),
        ("보도블럭", 1.3),
        ("도로보수", 1.3),
        ("시설보수", 1.3),
        ("노후시설", 1.3),
        ("파손", 1.1),
        ("입간판", 1.2),
        ("재도색", 1.3),
        ("도장", 1.1),
        # 개발/계획
        ("도시계획", 1.3),
        ("재개발", 1.4),
        ("재건축", 1.4),
        ("리모델링", 1.3),
        ("증개축", 1.5),
        ("신축", 1.2),
        ("개발사업", 1.3),
        ("주택건설", 1.3),
        # 구조 안전
        ("붕괴위험", 1.5),
        ("균열", 1.3),
        ("지반침하", 1.4),
        ("안전진단", 1.4),
        ("구조물", 1.1),
        # 기타
        ("조경", 0.9),
        ("상수도공사", 1.3),
        ("가스공사", 1.2),
        ("통신공사", 1.1),
        ("주거환경개선", 1.3),
    ],
}


@dataclass(frozen=True)
class TopicAnalysis:
    topic_type: TopicType
    confidence: float
    all_scores: dict[str, float]
    matched_keywords: list[str]
    is_ambiguous: bool
    secondary_topic: TopicType | None


class TopicAnalyzer:
    def __init__(
        self,
        keyword_map: dict[str, list[tuple[str, float]]] | None = None,
        negative_patterns: tuple[str, ...] | None = None,
    ) -> None:
        self._keyword_map = keyword_map or _DEFAULT_KEYWORD_MAP
        self._negative_patterns = negative_patterns or _NEGATIVE_PATTERNS

    def analyze(self, text: str) -> TopicAnalysis:
        normalized = _normalize_text(text, self._negative_patterns)
        scores: dict[str, float] = {}
        matched: list[str] = []

        for topic, weighted_keywords in self._keyword_map.items():
            topic_score = 0.0
            for keyword, weight in weighted_keywords:
                kw_norm = keyword.replace(" ", "")
                if kw_norm in normalized:
                    topic_score += weight
                    matched.append(keyword)
            scores[topic] = round(topic_score, 3)

        return _build_topic_analysis(scores, matched)

    def detect(self, text: str) -> TopicType:
        return self.analyze(text).topic_type


def analyze(text: str) -> TopicAnalysis:
    return _DEFAULT_ANALYZER.analyze(text)


def detect(text: str) -> TopicType:
    return _DEFAULT_ANALYZER.detect(text)


def _normalize_text(text: str, negative_patterns: tuple[str, ...]) -> str:
    cleaned = str(text or "").strip()
    for pattern in negative_patterns:
        cleaned = cleaned.replace(pattern, "")
    return cleaned.lower().replace(" ", "")


def _build_topic_analysis(
    scores: dict[str, float],
    matched: list[str],
) -> TopicAnalysis:
    if not any(v > 0 for v in scores.values()):
        return TopicAnalysis(
            topic_type="general",
            confidence=0.0,
            all_scores=scores,
            matched_keywords=[],
            is_ambiguous=False,
            secondary_topic=None,
        )

    sorted_topics = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_topic, top_score = sorted_topics[0]
    second_topic, second_score = sorted_topics[1]

    total = sum(scores.values())
    confidence = round(top_score / total, 3) if total > 0 else 0.0

    is_ambiguous = (
        top_score > 0
        and (top_score - second_score) < CONFIDENCE_AMBIGUITY_MARGIN * top_score
    )

    effective_topic: TopicType = (
        "general" if confidence < CONFIDENCE_MIN_THRESHOLD else top_topic  # type: ignore[assignment]
    )

    return TopicAnalysis(
        topic_type=effective_topic,
        confidence=confidence,
        all_scores=scores,
        matched_keywords=matched,
        is_ambiguous=is_ambiguous,
        secondary_topic=second_topic if is_ambiguous and effective_topic != "general" else None,  # type: ignore[arg-type]
    )


_DEFAULT_ANALYZER = TopicAnalyzer()
