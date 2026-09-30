# 버스 온톨로지 구축용 원천 자료 모음

- 정리일: 2026-09-29.
- 목적: **민원이 요구한 변경과 연결된 관계·대상의 변화를 확인할 지식 계층**의 원천 자료 보관.
- 전체 노선 비교·교통 시뮬레이션을 구축 선행 조건으로 두지 않음.
- 이번 작업: 공식 명세·본문·별표·데이터 수집과 기존 파일 색인. **온톨로지 작성, 개체·관계 추출, 지식그래프 생성, 서비스 반입 없음.**
- 전체 출처·원본 경로·수집 인자·크기·SHA-256: [sources.json](sources.json).
- 새 원본 29건 확보(본문 표 이미지 15건 포함), 기존 원본 18건은 이동·복제 없이 참조.
- 새 원본 폴더: `data/knowledge/raw/bus_ontology_sources_20260929/`. 기존 Git 제외 경로이며 목록·설명만 저장소 관리 대상.

## 1. 공식 기준과 관계도

출처: [국가법령정보센터의 버스정보시스템 기반정보 구축 및 관리요령](https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000198262), **2021-02-22 시행본**을 버전 고정하여 보관.

| 확보 파일 | 포함 내용 | 나중에 확인할 용도 |
|---|---|---|
| `bis_management_landing.html` | 공식 문서 버전과 조회 페이지 | 문서 식별·시행일 확인 |
| `bis_management_body.html`, `.txt` | 실제 조문 본문과 정의·정보 관리 기준 | 업무 용어와 데이터 관리 의미 확인 |
| `law_table_*.bmp` 15개 | 본문에서 참조하는 표 이미지 원본 | 텍스트 추출에서 빠지는 항목표 확인 |
| `law_annex_1.hwp` | 별표1 버스 정류장 및 노선 설정 방법 | 정류장·노선의 구분과 설정 기준 |
| `law_annex_2.hwp` | 별표2 버스 기반정보 코드부여 방법 | 식별자 체계 확인 |
| `law_annex_3.hwp` | 별표3 기반정보 관계도 | 공식 자료가 설명하는 관계 확인 |

- [로컬 읽기용 본문](../../../data/knowledge/raw/bus_ontology_sources_20260929/bis_management_local.html)은 내려받은 표 이미지에 연결한 사본. 원본 응답은 별도 보존.
- 별표3은 **정부가 제공한 기존 관계도**이며 이번 프로젝트가 구축한 온톨로지가 아님.
- HWP는 실제 파일 형식·용량 확인 후 보관. 전문 추출·해석은 아직 수행하지 않음.
- 이 자료를 최신 운행 상태나 특정 회사의 내부 규정으로 취급하지 않음.

## 2. 실제 버스정보시스템 명세

| 공식 자료 | 보관 파일 | 제공 내용과 확보 상태 |
|---|---|---|
| [BIS 운수회사별 운행노선 API](https://t-data.seoul.go.kr/category/dataviewopenapi.do?data_id=1050) | `bis_company_route_api.html` | 운수사 그룹ID와 노선ID. 명세 확보, 인증 API 응답 미수집 |
| [BIS 그룹 정보 API](https://t-data.seoul.go.kr/category/dataviewopenapi.do?data_id=1051) | `bis_company_api.html` | 그룹·운수회사 관련 필드. 명세 확보, 인증 API 응답 미수집 |
| [BIS 노선 정보 API](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1053) | `bis_route_api.html` | 노선 식별자·유형·기종점·배차·운행 여부·적용 예약일 등. 명세 확보 |
| [서울특별시 노선정보조회 서비스](https://www.data.go.kr/data/15000193/openapi.do) | `bus_route_api_portal.html` | 공식 서비스 설명·요청·출력 항목 페이지 확보 |

- 각 HTML에 읽기용 `.txt`와 표의 행·셀을 보존한 `.tables.json` 제공. 자체 클래스·관계·제약을 정의한 스키마가 아님.
- API 샘플은 설명용이며 실제 1127 운영 데이터로 사용하지 않음.
- 회사 그룹ID·회사명·노선ID의 의미는 각 명세에서 확인할 것. 이름만으로 서로 다른 회사를 합치지 않음.

## 3. 새로 확보한 운수회사 데이터

API 인증 없이 제공되는 **공식 파일 다운로드 경로**에서 CSV 원본 확보.

| 자료 | 원본 파일 | 실제 행 수 | 원본 열 |
|---|---|---:|---|
| [운수회사별 운행노선](https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=50) | `bis_company_routes.csv` | 1,962 | 운수회사ID, 노선ID |
| [그룹 정보](https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=51) | `bis_companies.csv` | 368 | 운수회사ID, 운수회사명, 운수회사이름, 권역코드, 지역ID |

- 카탈로그 HTML도 보관. API 미호출과 CSV 확보를 구분.
- 행 수를 서울 시내버스 회사 수로 해석하지 않음. 포함 권역과 회사 유형은 실제 사용 범위 선정 때 확인.
- 원본 필드마다 BOM 문자가 포함되어 있어 행·열 집계 시에만 제거. 원본 바이트는 그대로 보존.
- CSV에 행별 유효시점 없음. 카탈로그 수정일·수집일을 계약·운영 관계의 적용일로 바꾸지 않음.
- 아직 기존 1127 자료와 결합하거나 회사 관계를 그래프에 등록하지 않음.

## 4. 기존 데이터 재사용 색인

다음 파일은 이미 확보되어 있어 `sources.json`에서 기존 위치와 해시로 참조. 원본을 새 폴더에 중복 저장하지 않음.

| 자료 묶음 | 실제 파일·위치 | 내용 |
|---|---|---|
| 노선·정류장 원장 | `data/knowledge/raw/demo_complaints_20260929/seoul_route_order_20260902.xlsx`, `seoul_stops_20260902.xlsx` | 노선ID·정차순번·정류장ID·ARS·명칭·좌표 |
| 시간대별 승하차 | `data/knowledge/raw/demo_preparation_20260929/seoul_ridership_202608.csv` | 2026년8월 노선·정류장별 시간대 승하차. 42,578행 |
| 도봉 보행망·코드표 | `data/knowledge/raw/demo_selection_20260929/seoul_walk_dobong.json`, `seoul_walk_codes.xlsx` | 보행 노드·링크·통행유형 코드 |
| 강북·노원 보행망 | `data/knowledge/raw/demo_preparation_20260929/seoul_walk_gangbuk.json`, `seoul_walk_nowon.json` | 인접 지역 원본 |
| 공식 데이터 설명 | 기존 노선·정류장·보행 카탈로그, 새 `seoul_ridership_catalog.html` | 필드·기준시점·제공 조건 |

- 이미 만든 집계·파생 연결 자료는 [기존 준비 묶음](../demo_preparation_20260929/README.md)에 별도 보관. 원본과 분석 가정을 혼합하지 않음.
- 보행망은 관계를 확인할 보조 자료로 보관. 전체 보행망 복구나 거리 계산은 이번 수집의 완료 조건이 아님.

## 5. 업무 문서와 실제 민원

| 자료 | 보관 위치 | 구분 |
|---|---|---|
| 2025년 도봉보건소 정차 변경 제안·승인 자료 | `data/knowledge/raw/demo_selection_20260929/dobong_proposal.html`, `dobong_approved.html` | 실제 행정 변경 자료 |
| 도봉보건소 접근 안내 | 같은 폴더 `dobong_health_access.html` | 시설의 공식 교통 안내 |
| 2026년1127 노선 변경 민원·기관 답변 | `data/knowledge/raw/demo_complaints_20260929/dobong_1127_complaint.html` | 시민 요청과 기관 검토 의견 |
| 시민 첨부 지도4장 | 같은 폴더 `IMG_0258/0259/0261/0262.jpeg` | 개략 제안 자료. 승인 노선·정밀 경로 아님 |

- 2025년 정차 변경과 2026년 민원은 별도 사건.
- 시민 요청·기관 답변·확정된 행정 조치를 구분. 원문 개인 메타데이터는 추후 생성 입력에 일괄 포함하지 않음.
- 기관 문서에 나타난 업무 역할과 기준을 나중에 읽을 수 있도록 보관한 단계. 담당 부서·운수회사의 책임 관계를 이번에 추출하거나 확정하지 않음.

## 6. 확보하지 않은 자료

- 버스회사 내부 배차표·인력·정비·결재·비용 원장: 미확보. 현재 공개자료 묶음이 내부 회사 시스템 전체를 복원한다고 주장하지 않음.
- API 실시간 응답: 미수집. 인증키 신청이나 계정 변경 없음.
- 시설 출입구와 실제 보행 접속 확정 자료: 아직 미완성. 기존 정류장 좌표를 시설 출입구로 대체하지 않음.
- LH 자료는 [운영 자료 조사와 현재 범위](../../../docs/70_research/company_knowledge/lh_operational_data_availability_2026-09-29.md), 기존 LH 파일럿을 유지. 이번 신규 수집은 버스 자료에 집중.

## 7. 완료와 다음 작업

- 선정 이유: 공식 용어·식별자·관계도, 실제 시스템 필드, 실제 레코드, 업무 변경 문서를 함께 읽을 수 있도록 구성.
- 확인: 원본 존재·해시, CSV 행과 열, HWP 파일 형식, 본문 표 이미지 확보 여부 확인. 온톨로지 품질 평가나 시스템 구현은 수행하지 않음.
- 다음: 구축 요청 시 이 묶음부터 읽고 필요한 자료 범위를 선택. 전체 노선 변경안 확정은 선행하지 않음.
- 현재 사용자 결정이 필요한 사항 없음. 커밋·푸시 없음.
