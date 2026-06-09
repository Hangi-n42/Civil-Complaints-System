"""build_department_master 보일러플레이트 필터 — 도메인 앵커 예외 (#346)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bdm", str(Path(__file__).resolve().parents[3] / "scripts" / "build_department_master.py"))
bdm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bdm)


def test_domain_task_with_총괄_is_kept():
    # 버그 재현: "건설기계 위임 사무 총괄" 이 총괄$ 로 오제거되던 케이스
    assert bdm.is_boilerplate("건설기계 위임 사무 총괄") is False


def test_generic_총괄_still_removed():
    assert bdm.is_boilerplate("감사공직자 워크숍 총괄") is True
    assert bdm.is_boilerplate("업무 총괄") is True


def test_hard_boilerplate_not_exempted_even_with_domain_word():
    # 하드 패턴(업무추진비/청사관리)은 도메인어가 있어도 항상 제거
    assert bdm.is_boilerplate("건설 부서 업무추진비 집행") is True
    assert bdm.is_boilerplate("도로과 청사 관리") is True


def test_non_boilerplate_unchanged():
    assert bdm.is_boilerplate("건설기계 조종사면허 적성검사 갱신 안내") is False
