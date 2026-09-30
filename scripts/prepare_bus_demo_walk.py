"""Prepare walking evidence and unapproved stop attachment candidates; no impact calculation.

Run: .venv/bin/python scripts/prepare_bus_demo_walk.py [--fetch-missing]
Missing endpoint downloads are limited to IDs used by the original Dobong links.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.parse
import urllib.request

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/knowledge/raw/demo_preparation_20260929"
OUT = ROOT / "data/processed/knowledge_demo_preparation_20260929"
CONFIG = ROOT / "configs/knowledge/demo_preparation_20260929"
INPUTS = [ROOT / "data/knowledge/raw/demo_selection_20260929/seoul_walk_dobong.json",
          RAW / "seoul_walk_gangbuk.json", RAW / "seoul_walk_nowon.json"]
URL = "https://datafile.seoul.go.kr/bigfile/iot/sheet/json/download.do"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def missing(links, nodes):
    return [r for r in links if any(r[k] not in nodes for k in ("bgng_lnkg_id", "end_lnkg_id"))]


def merge(rows):
    unique, conflicts, duplicates = {}, {}, 0
    for row in rows:
        key = (row["node_type"], row["node_id"] if row["node_type"] == "NODE" else row["lnkg_id"])
        # Collection timestamps do not change the represented geometry or attributes.
        value = {k: v for k, v in row.items() if k != "work_dttm"}
        if key in unique:
            duplicates += 1
            if {k: v for k, v in unique[key].items() if k != "work_dttm"} != value:
                conflicts.setdefault(key, [unique[key]]).append(row)
        else:
            unique[key] = row
    for key in conflicts:
        unique.pop(key)
    return list(unique.values()), [{"kind": k[0], "id": k[1], "rows": v} for k, v in conflicts.items()], duplicates


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def point(wkt):
    match = re.fullmatch(r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)", wkt)
    if not match:
        raise ValueError(f"Unsupported node geometry: {wkt}")
    return tuple(map(float, match.groups()))


def sheet(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    rows = workbook.active.values
    headers = next(rows)
    result = [dict(zip(headers, row)) for row in rows]
    workbook.close()
    return result


def main(fetch_missing=False):
    original = read(INPUTS[0])["DATA"]
    original_links = [r for r in original if r["node_type"] == "LINK"]
    original_nodes = {r["node_id"] for r in original if r["node_type"] == "NODE"}
    base, conflicts, duplicates = merge([r for p in INPUTS for r in read(p)["DATA"]])
    nodes = {r["node_id"]: r for r in base if r["node_type"] == "NODE"}
    incomplete = missing(original_links, nodes)
    missing_ids = sorted({r[k] for r in incomplete for k in ("bgng_lnkg_id", "end_lnkg_id") if r[k] not in nodes})
    sources, recovered = [], []
    for node_id in missing_ids:
        path = RAW / f"walk_node_{node_id}.json"
        invalid_path = path.with_suffix(".response.txt")
        parameters = dict(srvType="S", infId="OA-21208", serviceKind="1", pageNo="1",
                          gridTotalCnt="", ssUserId="SAMPLE_VIEW", strWhere="", strOrderby="SGG_CD ASC",
                          filterCol="NODE_ID", txtFilter=str(node_id))
        if not path.exists() and not invalid_path.exists() and fetch_missing:
            request = urllib.request.Request(URL, data=urllib.parse.urlencode(parameters).encode())
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            try:
                assert isinstance(json.loads(payload)["DATA"], list)
                path.write_bytes(payload)
            except (ValueError, KeyError, AssertionError):
                invalid_path.write_bytes(payload)
        if invalid_path.exists():
            sources.append(dict(source_id=invalid_path.name, url=URL, method="POST", parameters=parameters,
                                local_path=str(invalid_path.relative_to(ROOT)), bytes=invalid_path.stat().st_size,
                                sha256=hashlib.sha256(invalid_path.read_bytes()).hexdigest(),
                                requested_node_id=node_id, status="invalid_json_downloads_stopped",
                                exact_matches=None))
            break
        if not path.exists():
            continue
        rows = read(path)["DATA"]
        # The public filter is substring matching: never accept similar IDs.
        exact = [r for r in rows if r["node_type"] == "NODE" and r["node_id"] == node_id]
        recovered.extend(exact)
        sources.append(dict(source_id=path.name, url=URL, method="POST", parameters=parameters,
                            local_path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            saved_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                            requested_node_id=node_id, returned_rows=len(rows), exact_matches=len(exact),
                            rights="서울시 공공누리 1유형 출처표시. 원본은 로컬 보관"))
    merged, extra_conflicts, extra_duplicates = merge(base + recovered)
    conflicts.extend(extra_conflicts)
    nodes = {r["node_id"]: r for r in merged if r["node_type"] == "NODE"}
    links = [r for r in merged if r["node_type"] == "LINK"]
    incomplete = missing(links, nodes)
    bad_ids = {r["lnkg_id"] for r in incomplete}
    walkable = [r for r in links if str(r["lnkg_type_cd"]).startswith("1") and r["lnkg_id"] not in bad_ids]
    connected = {r[k] for r in walkable for k in ("bgng_lnkg_id", "end_lnkg_id")}
    node_points = {key: point(nodes[key]["node_wkt"]) for key in connected}

    route_path = ROOT / "data/knowledge/raw/demo_complaints_20260929/seoul_route_order_20260902.xlsx"
    stop_path = ROOT / "data/knowledge/raw/demo_complaints_20260929/seoul_stops_20260902.xlsx"
    route = [r for r in sheet(route_path) if str(r["ROUTE_ID"]) == "100100143"]
    route_ids = {r["NODE_ID"] for r in route}
    registry = sheet(stop_path)
    registry_by_id = {r["NODE_ID"]: r for r in registry}
    route_points = [(registry_by_id[r["NODE_ID"]]["X좌표"], registry_by_id[r["NODE_ID"]]["Y좌표"]) for r in route]
    proposed_ars = {r["ars_id"] for r in read(CONFIG / "bus_candidate_points.json")["points"]}
    # ponytail: a local preparation batch, exhaustive distance checks avoid a spatial-index dependency.
    candidates = []
    for stop in registry:
        coordinate = (stop["X좌표"], stop["Y좌표"])
        if stop["NODE_ID"] not in route_ids and str(stop["ARS_ID"]).zfill(5) not in proposed_ars and min(distance(coordinate, p) for p in route_points) > 500:
            continue
        nearest = sorted(((distance(coordinate, p), key) for key, p in node_points.items()))[:3]
        candidates.append({"stop_node_id": stop["NODE_ID"], "ars_id": str(stop["ARS_ID"]).zfill(5),
                           "name": stop["정류소명"], "coordinate": coordinate,
                           "scope": "current_1127" if stop["NODE_ID"] in route_ids else "proposed_unconfirmed" if str(stop["ARS_ID"]).zfill(5) in proposed_ars else "nearby_500m_collection_candidate",
                           "review_status": "unreviewed_roadside_crossing_and_entrance_not_confirmed",
                           "candidates": [{"walk_node_id": key, "straight_line_m": round(d, 2),
                                           "coordinate": node_points[key], "node_type_cd": nodes[key]["node_type_cd"]}
                                          for d, key in nearest]})
    summary = {"status": "prepared_not_attached_not_routed", "walking_reference_year": 2020,
               "bus_reference_date": "2026-09-02", "source_paths": [str(p.relative_to(ROOT)) for p in INPUTS],
               "original_dobong_missing_links": len(missing(original_links, original_nodes)),
               "after_three_district_merge_missing_dobong_links": len(missing(original_links, {r['node_id'] for r in base if r['node_type']=='NODE'})),
               "targeted_missing_node_ids": missing_ids, "targeted_downloads": len(sources),
               "unqueried_node_ids": sorted(set(missing_ids) - {s['requested_node_id'] for s in sources}),
               "exact_nodes_recovered": len(recovered), "final_missing_dobong_links": len(missing(original_links, nodes)),
               "final_missing_dobong_link_ids": [r["lnkg_id"] for r in missing(original_links, nodes)],
               "merged_nodes": len(nodes), "merged_links": len(links), "merged_missing_endpoint_links": len(incomplete),
               "unresolved_links_by_source_district": dict(Counter(r['sgg_nm'] for r in incomplete)),
               "walkable_complete_links": len(walkable), "link_type_counts": dict(Counter(str(r['lnkg_type_cd']) for r in links)),
               "duplicate_rows": duplicates + extra_duplicates, "conflicting_ids": len(conflicts),
               "current_1127_stop_rows": len(route), "current_1127_unique_stops": len(route_ids),
               "stop_attachment_candidate_rows": len(candidates), "confirmed_attachments": 0,
               "nearby_collection_radius_m": 500, "candidate_distance_kind": "straight_line_not_walking_distance",
               "missing_links_policy": "excluded_from_walkable_output_and_retained_as_unresolved",
               "processed_path": str(OUT.relative_to(ROOT))}
    save(OUT / "walk_network.json", {"nodes": list(nodes.values()), "walkable_complete_links": walkable,
                                     "unresolved_links": incomplete, "id_conflicts": conflicts})
    save(OUT / "stop_attachment_candidates.json", {"route_stop_rows": route, "stops": candidates,
                                                   "note": "직선거리로 정렬한 후보만 제공. 도로 측면·횡단·출입구 확인 전에는 보행 접속으로 확정하지 않음. 제안 정류장도 시민 지도와 ID 대응 확인 필요."})
    save(CONFIG / "walking_sources.json", {"sources": sources})
    save(CONFIG / "walk_summary.json", summary)
    # Runnable checks cover ID namespaces, pedestrian filtering and unresolved endpoints.
    assert all(r[k] in nodes for r in walkable for k in ("bgng_lnkg_id", "end_lnkg_id"))
    assert all(str(r["lnkg_type_cd"]).startswith("1") for r in walkable)
    assert len(route) == 60 and route_ids <= {r["stop_node_id"] for r in candidates}
    assert proposed_ars <= {r["ars_id"] for r in candidates}
    assert distance((127, 37), (127, 37)) == 0
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-missing", action="store_true")
    main(parser.parse_args().fetch_missing)
