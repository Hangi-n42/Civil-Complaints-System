"""Join the frozen Seoul route order to monthly ridership for the 1127 demo.

Run from the repository: python scripts/prepare_bus_demo_ridership.py
Raw inputs and derived tables stay in data/knowledge; summary is reviewable.
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/knowledge/raw/demo_complaints_20260929"
NEW = ROOT / "data/knowledge/raw/demo_preparation_20260929"
OUT = ROOT / "data/processed/knowledge_demo_preparation_20260929"
CONFIG = ROOT / "configs/knowledge/demo_preparation_20260929"


def sheet(name):
    workbook = load_workbook(RAW / name, read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    header = next(rows)
    result = [dict(zip(header, row)) for row in rows if any(v is not None for v in row)]
    workbook.close()
    return result


def save_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    routes = sheet("seoul_route_order_20260902.xlsx")
    stops = {int(r["NODE_ID"]): r for r in sheet("seoul_stops_20260902.xlsx")}
    with (NEW / "seoul_ridership_202608.csv").open(encoding="cp949", newline="") as handle:
        usage = list(csv.DictReader(handle))
    assert {r["사용년월"] for r in usage} == {"202608"}
    usage_index = defaultdict(list)
    for row in usage:
        usage_index[(row["노선번호"], row["표준버스정류장ID"])].append(row)
    target = [r for r in routes if str(r["노선명"]) == "1127"]
    target_nodes = {int(r["NODE_ID"]) for r in target}
    proposal = json.loads((CONFIG / "bus_candidate_points.json").read_text(encoding="utf-8"))
    proposal_nodes = {int(r["node_id"]) for r in proposal["points"]}
    # These are candidates mentioned in the complaint, not proven substitutes.
    mentioned = {"1126", "1119", "1120", "1138", "도봉01", "도봉06",
                 "107", "140", "141", "142", "150", "160", "36", "118"}
    selected = {str(r["노선명"]) for r in routes if int(r["NODE_ID"]) in target_nodes | proposal_nodes} | mentioned
    occurrences = Counter((str(r["노선명"]), str(r["NODE_ID"])) for r in routes)
    joined = []
    for route in routes:
        name, node = str(route["노선명"]), str(route["NODE_ID"])
        if name not in selected:
            continue
        matches = usage_index[(name, node)]
        # The monthly source preserves occurrence order in 역명, e.g. 한일병원(00028).
        # Use it only to distinguish repeated physical stops; unresolved duplicates stay visible.
        if len(matches) > 1:
            by_sequence = [r for r in matches if re.search(r"\((\d+)\)$", r["역명"])
                           and int(re.search(r"\((\d+)\)$", r["역명"]).group(1)) == int(route["순번"])]
            if len(by_sequence) == 1:
                matches = by_sequence
        stop = stops.get(int(node))
        status = "matched" if len(matches) == 1 else ("missing" if not matches else "ambiguous")
        use = matches[0] if status == "matched" else None
        record = {
            "route_id": route["ROUTE_ID"], "route_name": name,
            "sequence": route["순번"], "node_id": node,
            "ars_id": str(route["ARS_ID"]).zfill(5), "stop_name": route["정류소명"],
            "longitude": route["X좌표"], "latitude": route["Y좌표"],
            "stop_registry_match": stop is not None,
            "ridership_status": status, "ridership_month": "202608",
            "ridership_ars_id": use["버스정류장ARS번호"].zfill(5) if use else "",
            "ridership_ars_matches_route": str(route["ARS_ID"]).zfill(5) == use["버스정류장ARS번호"].zfill(5) if use else "",
            "ridership_source_stop_label": use["역명"] if use else "",
            "monthly_boardings": sum(int(use[k]) for k in use if k.endswith("승차총승객수")) if use else "",
            "monthly_alightings": sum(int(use[k]) for k in use if k.endswith("하차총승객수")) if use else "",
            "same_route_node_occurrences": occurrences[(name, node)],
            "shares_current_1127_physical_stop": int(node) in target_nodes,
            "serves_proposed_candidate_stop": int(node) in proposal_nodes,
        }
        joined.append(record)
    matched_sources = [(r["route_name"], r["node_id"], r["ridership_source_stop_label"])
                       for r in joined if r["ridership_status"] == "matched"]
    assert len(matched_sources) == len(set(matched_sources)), "An observed usage row was reused for multiple occurrences"
    save_csv("route_stops_with_ridership.csv", joined)
    save_csv("1127_current_with_ridership.csv", [r for r in joined if r["route_name"] == "1127"])
    shared = [r for r in joined if r["route_name"] != "1127" and r["shares_current_1127_physical_stop"]]
    save_csv("shared_stop_alternative_candidates.csv", shared)
    save_csv("proposal_stop_ridership_candidates.csv", [r for r in joined if r["serves_proposed_candidate_stop"]])
    # Preserve all hourly source columns separately. Do not duplicate monthly usage per occurrence.
    used_keys = {(r["route_name"], r["node_id"]) for r in joined}
    save_csv("selected_hourly_ridership.csv", [r for r in usage if (r["노선번호"], r["표준버스정류장ID"]) in used_keys])
    alternatives = []
    for name in sorted({r["route_name"] for r in joined} - {"1127"}):
        rows = [r for r in joined if r["route_name"] == name]
        alternatives.append({
            "route_name": name, "route_id": rows[0]["route_id"],
            "mentioned_candidate": name in mentioned,
            "ordered_stop_rows": len(rows),
            "shared_1127_node_ids": sorted({r["node_id"] for r in rows if r["shares_current_1127_physical_stop"]}),
            "proposed_candidate_node_ids": sorted({r["node_id"] for r in rows if r["serves_proposed_candidate_stop"]}),
            "stop_registry_matched_rows": sum(r["stop_registry_match"] for r in rows),
            "ridership_matched_rows": sum(r["ridership_status"] == "matched" for r in rows),
            "status": "candidate_not_confirmed_alternative",
        })
    (OUT / "alternative_routes.json").write_text(json.dumps(alternatives, ensure_ascii=False, indent=2) + "\n")
    own = [r for r in joined if r["route_name"] == "1127"]
    change = json.loads((CONFIG / "bus_change_proposal.json").read_text(encoding="utf-8"))
    removed_orders = {r["baseline_order"] for r in change["baseline_stops"] if r["proposal_status"] == "remove_candidate"}
    removal_candidates = [r for r in own if r["sequence"] in removed_orders]
    save_csv("removal_candidates_current_usage.csv", removal_candidates)
    # One bounded check of the selected baseline and exact join, not a general data test suite.
    assert len(own) == 60 and len({r["node_id"] for r in own}) == 60
    assert all(r["stop_registry_match"] and r["ridership_status"] == "matched" for r in own)
    assert all(r["ars_id"] == r["ridership_ars_id"] for r in own)
    summary = {
        "status": "baseline_join_complete_proposal_pending", "ridership_source_rows": len(usage),
        "route_reference_date": "2026-09-02", "ridership_month": "2026-08",
        "join_key": ["route_name = 노선번호", "NODE_ID = 표준버스정류장ID", "중복은 역명 내 정차 순번이 유일하게 일치할 때만 구분"],
        "target_route": "1127", "target_rows": len(own), "target_exact_matches": len(own),
        "monthly_boardings": sum(r["monthly_boardings"] for r in own),
        "monthly_alightings": sum(r["monthly_alightings"] for r in own),
        "removal_candidates_current_usage": {
            "ordered_stops": len(removal_candidates),
            "monthly_boardings": sum(r["monthly_boardings"] for r in removal_candidates),
            "monthly_alightings": sum(r["monthly_alightings"] for r in removal_candidates),
            "meaning": "제외 후보 구간의 기존 이용 기록이며 피해 인원이나 변경 후 감소량이 아님"},
        "selected_routes": len(alternatives) + 1, "selected_route_stop_rows": len(joined),
        "selected_stop_registry_matches": sum(r["stop_registry_match"] for r in joined),
        "selected_ridership_status": dict(Counter(r["ridership_status"] for r in joined)),
        "matched_ars_discrepancies": [{"route_name": r["route_name"], "node_id": r["node_id"],
                                      "route_ars_id": r["ars_id"], "ridership_ars_id": r["ridership_ars_id"]}
                                     for r in joined if r["ridership_ars_matches_route"] is False],
        "shared_target_stop_rows": len(shared),
        "shared_target_route_count": len({r["route_name"] for r in shared}),
        "shared_target_stop_registry_matches": sum(r["stop_registry_match"] for r in shared),
        "shared_target_ridership_status": dict(Counter(r["ridership_status"] for r in shared)),
        "proposal_candidate_stop_count": len(proposal_nodes),
        "proposal_candidate_stops_with_route_rows": len({int(r["node_id"]) for r in joined if r["serves_proposed_candidate_stop"]}),
        "proposal_candidate_stops_with_any_matched_ridership": len({int(r["node_id"]) for r in joined if r["serves_proposed_candidate_stop"] and r["ridership_status"] == "matched"}),
        "mentioned_routes_not_in_route_file": sorted(mentioned - {str(r["노선명"]) for r in routes}),
        "alternatives": alternatives,
        "limits": ["월간 교통카드 승하차 건수이며 고유 인원·피해 인원·변경 후 수요가 아님",
                   "8월 이용 기록과 9월 2일 노선 간 시점 차이 보존",
                   "동일 노선·정류장 복수 정차는 이용량을 중복 합산하지 말 것",
                   "같은 정류장 경유는 대체 가능성 후보이며 방향·목적지·시간 검토 전 확정하지 않음"],
        "output_directory": str(OUT.relative_to(ROOT)),
    }
    (CONFIG / "ridership_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "alternatives"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
