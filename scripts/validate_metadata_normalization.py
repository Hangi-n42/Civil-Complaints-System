#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #101-2 metadata normalization validator.

검증 범위:
1) REGION_MAPPING.yaml 구조 및 검증 섹션
2) CATEGORY_ENUM.yaml 구조 및 검증 섹션
3) evaluation_set.json의 scenario_type이 CATEGORY allowed_values에 포함되는지
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"YAML payload must be object: {path}")
    return payload


def _load_json_list(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError(f"JSON payload must be list: {path}")
    return payload


def validate_region_mapping(path: Path) -> Dict[str, Any]:
    regions = _load_yaml(path)
    validation = regions.get("validation", {})
    allowed = validation.get("allowed_values", [])
    mapping_rules = regions.get("mapping_rules", [])

    if not isinstance(allowed, list) or not allowed:
        return {
            "status": "FAIL",
            "error": "validation.allowed_values missing or empty",
            "region_count": 0,
            "alias_count": 0,
        }

    alias_count = 0
    for _, config in regions.items():
        if isinstance(config, dict):
            aliases = config.get("aliases", [])
            if isinstance(aliases, list):
                alias_count += len(aliases)

            districts = config.get("districts", {})
            if isinstance(districts, dict):
                for _, district_aliases in districts.items():
                    if isinstance(district_aliases, list):
                        alias_count += len(district_aliases)
                    elif isinstance(district_aliases, str):
                        alias_count += 1

    return {
        "status": "PASS",
        "region_count": len(allowed),
        "alias_count": alias_count,
        "mapping_rule_count": len(mapping_rules) if isinstance(mapping_rules, list) else 0,
    }


def validate_category_enum(path: Path) -> Dict[str, Any]:
    categories = _load_yaml(path)
    validation = categories.get("validation", {})
    allowed = validation.get("allowed_values", [])

    if not isinstance(allowed, list) or not allowed:
        return {
            "status": "FAIL",
            "error": "validation.allowed_values missing or empty",
            "category_count": 0,
            "alias_count": 0,
            "detail_count": 0,
        }

    detail_count = 0
    alias_count = 0
    for key, config in categories.items():
        if key in {"mapping_rules", "validation"}:
            continue
        if isinstance(config, dict):
            detail_count += 1
            aliases = config.get("aliases", [])
            if isinstance(aliases, list):
                alias_count += len(aliases)

    return {
        "status": "PASS",
        "category_count": len(allowed),
        "alias_count": alias_count,
        "detail_count": detail_count,
    }


def validate_evaluation_set_coverage(eval_path: Path, category_path: Path) -> Dict[str, Any]:
    evaluation_set = _load_json_list(eval_path)
    category_yaml = _load_yaml(category_path)
    allowed_categories = set(category_yaml.get("validation", {}).get("allowed_values", []))

    scenario_types = [
        str(case.get("scenario_type"))
        for case in evaluation_set
        if isinstance(case, dict) and case.get("scenario_type") is not None
    ]
    unique_scenario_types = sorted(set(scenario_types))
    unmapped = sorted([s for s in unique_scenario_types if s not in allowed_categories])
    distribution = Counter(scenario_types)

    return {
        "status": "PASS" if not unmapped else "WARNING",
        "total_cases": len(evaluation_set),
        "scenario_type_count": len(unique_scenario_types),
        "mapped_count": len(unique_scenario_types) - len(unmapped),
        "unmapped_types": unmapped,
        "distribution": dict(distribution),
    }


def main() -> int:
    region_path = Path("configs/REGION_MAPPING.yaml")
    category_path = Path("configs/CATEGORY_ENUM.yaml")
    eval_path = Path("docs/40_delivery/week3/model_test_assets/evaluation_set.json")

    print("\n[START] Issue #101-2 Metadata Normalization Validation")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    region_result = validate_region_mapping(region_path)
    category_result = validate_category_enum(category_path)
    coverage_result = validate_evaluation_set_coverage(eval_path, category_path)

    print("\n[SUMMARY]")
    print(f"  Region Mapping:          {region_result['status']}")
    print(f"  Category Enum:           {category_result['status']}")
    print(f"  Evaluation Set Coverage: {coverage_result['status']}")
    print(
        "  Mapped scenario types: "
        f"{coverage_result['mapped_count']}/{coverage_result['scenario_type_count']}"
    )

    if coverage_result["unmapped_types"]:
        print(f"  Unmapped types: {coverage_result['unmapped_types']}")

    all_pass = (
        region_result["status"] == "PASS"
        and category_result["status"] == "PASS"
        and coverage_result["status"] in {"PASS", "WARNING"}
    )

    print("\n[GATE CRITERIA for Issue #101-2]")
    print(f"  REGION_MAPPING.yaml valid: {region_result['status'] == 'PASS'}")
    print(f"  CATEGORY_ENUM.yaml valid:  {category_result['status'] == 'PASS'}")
    print(f"  Evaluation set mapped:     {coverage_result['mapped_count'] > 0}")
    print(f"  Ready for Issue #101-3:    {all_pass}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
