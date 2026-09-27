# 회사 지식 PRD 재사용 조사 — 문서 파싱·원문 위치·변경 비교

조사일: 2026-09-26. 대상: `company_knowledge_prd.md` FR-01·02·07, Python 3.11.9, Mac/Windows 네이티브, 기존 의존성 유지. **공식 문서·배포 메타데이터 조사이며 설치·한국어 문서 비교 실험은 수행하지 않았다.** 아래 채택 판단은 설계 제안이다. 라이선스 표기는 공개 프로젝트의 선언이며 실제 배포 형태에 대한 법률 판단이 아니다.

## 결론

**P0는 HWPX ZIP/XML + 표를 다루는 가벼운 PDF 파서 하나 + 표준 라이브러리 변경 비교로 시작한다.** 표·셀 원문 대조가 필요한 LH 자료에는 `pdfplumber`가 직접 도입 우선 후보다. 단순 본문 PDF만 다룬다면 `pypdf`가 더 작다. 두 파서를 처음부터 함께 넣을 이유는 없다. `Docling`은 가벼운 파서가 실제 복잡 표에서 실패하고 해당 자료가 필수일 때 비교할 조건부 후보로 둔다.

현재 프로젝트 `.venv`는 Python 3.11.9다. 아래 PDF·HWPX·diff 외부 패키지는 모두 미설치이며 `requirements.txt`에도 없다. `Pillow==11.3.0`, `torch==2.5.1`, `onnxruntime==1.24.3`, `transformers==4.46.3`은 기존 고정값이다. 호스트의 문서 작업 도구가 있더라도 프로젝트 의존성으로 간주하지 않았다.

## 후보 7개 비교

| 후보 | 확인한 기능·원문 위치 | Python·OS·라이선스/리소스 | 판정과 한계 |
| --- | --- | --- | --- |
| **1. 표준 라이브러리 HWPX/CSV/HTML + hash/difflib** | HWPX는 ZIP/XML이므로 `zipfile`·`ElementTree`로 구역/문단/표/셀 구조를 읽는 어댑터를 만들 수 있다. CSV 행/열, 선택 HTML 요소 경로, `hashlib` 해시와 `difflib` 변경 구간을 연결한다. [한컴 형식 설명](https://tech.hancom.com/hwpxformat/), [Python difflib](https://docs.python.org/3.11/library/difflib.html) | Python 3.11 표준 라이브러리, 추가 모델·한컴 프로그램 불필요. 선택 비교 후보 `python-hwpx` 6.5.0은 Python>=3.10, Apache-2.0, `lxml` 의존. [공식 패키지 저장소](https://github.com/airmang/python-hwpx), [배포 정보](https://pypi.org/pypi/python-hwpx/6.5.0/json) | **직접 재사용 우선.** ZIP/XML을 읽는 것과 한글의 렌더링·페이지 나눔을 재현하는 것은 다르다. 구형 바이너리 HWP는 지원하지 않는다. 복잡 중첩표·각주 때문에 자체 어댑터가 커질 때만 `python-hwpx`를 실제 샘플로 비교한다. 이 라이브러리는 한컴 공식 SDK가 아닌 커뮤니티 구현이다. |
| **2. pypdf** | PDF 페이지별 본문/메타데이터 추출, 레이아웃 모드·visitor 제공. 복잡 PDF의 visitor 좌표가 틀릴 수 있음을 문서가 명시한다. OCR·표 의미구조 인식 엔진은 아니다. [추출 문서](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) | 조회 버전 6.19.0, Python>=3.9, BSD-3-Clause, 순수 Python. 기본 본문 추출에 별도 모델·시스템 PDF 프로그램 불필요. [저장소](https://github.com/py-pdf/pypdf), [메타데이터](https://pypi.org/pypi/pypdf/6.19.0/json) | **본문 PDF에 직접 도입 가능 후보.** P0의 PDF 페이지 위치 요구에는 맞지만 표의 행/셀 의미 보존까지 충족했다고 보지 않는다. 한국어 폰트 인코딩·읽기 순서·다단문서 정확도 미확인. |
| **3. pdfplumber** | 문자·단어 좌표, 페이지, 선/사각형, 표의 `cells/rows/columns/bbox`, 시각 대조 도구 제공. 텍스트 PDF에 적합하고 OCR은 제공하지 않는다. [기능/API](https://github.com/jsvine/pdfplumber/blob/stable/README.md), [MIT 라이선스](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt) | **최신 0.11.10의 Pillow>=12.2.0은 기존 11.3.0과 충돌.** 0.11.9는 Pillow>=9.1, pdfminer.six==20251230, pypdfium2>=4.18.0, Python>=3.8. [0.11.10](https://pypi.org/pypi/pdfplumber/0.11.10/json), [0.11.9](https://pypi.org/pypi/pdfplumber/0.11.9/json) | **LH 표 PDF의 직접 도입 1순위 후보는 0.11.9.** 확인한 Pillow 제약을 충족한다는 뜻이며 전체 의존성 해결·양 OS 실행이 검증된 것은 아니다. 선 없는 표, 병합 셀, 한 페이지에 인쇄 두 쪽, 다페이지 표는 대조가 필요하다. 최신판으로 기존 Pillow를 일괄 변경하지 않는다. |
| **4. PyMuPDF / pymupdf4llm** | PyMuPDF의 페이지·단어·표/셀 좌표, 4LLM의 페이지 청크·JSON 요소 bbox를 재사용할 수 있다. Markdown만 저장하면 위치 정보가 충분하지 않다. [Page API](https://pymupdf.readthedocs.io/en/latest/page.html#Page.find_tables), [4LLM API/범위](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) | 조회 버전 각각 1.28.2, Python>=3.10. Mac/Windows 배포 지원. **AGPL-3.0 또는 Artifex 상용 라이선스**; 4LLM이 기본 의존하는 `pymupdf-layout`도 별도 확인 대상이며 현재 같은 이중 라이선스를 선언한다. [설치](https://pymupdf.readthedocs.io/en/latest/installation.html), [라이선스](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright), [Layout](https://pypi.org/project/pymupdf-layout/) | **기능 후보이나 P0 기본 채택 보류.** 라이선스 정책 선택이 추가된다. HWP/HWPX 지원은 일반 OSS PDF 경로가 아니라 **PyMuPDF Pro 확장** 설명이다. 이를 무료 HWPX 대체로 계산하지 않는다. 4LLM은 현재 자동 OCR이 기본이므로 P0 비교에서는 명시적으로 끄고 빈 추출을 실패로 표시해야 한다. |
| **5. Docling** | `DoclingDocument`의 계층·읽기 순서·provenance, 페이지/bbox/문자범위, `TableCell`의 셀 범위·bbox를 사용할 수 있다. JSON과 원본을 보존해야 한다. 공식 지원 목록에서 HWP/HWPX 전용 지원은 확인되지 않았다. [문서 모델](https://docling-project.github.io/docling/concepts/docling_document/), [셀 타입](https://github.com/docling-project/docling-core/blob/main/docling_core/types/doc/document.py), [형식 목록](https://docling-project.github.io/docling/usage/supported_formats/) | 조회 버전 2.130.0, Python>=3.10,<4, Mac/Windows 지원 선언. 코드 MIT, 모델은 각각 별도 라이선스. 표 모델 저장소 `docling-project/docling-models`는 CDLA-Permissive-2.0. 표/레이아웃 모델 다운로드·실행 비용이 있다. [저장소](https://github.com/docling-project/docling), [모델](https://huggingface.co/docling-project/docling-models), [오프라인 설정](https://docling-project.github.io/docling/usage/advanced_options/) | **복잡 표에 조건부 도입.** 타입이 provenance를 표현한다는 사실이 모든 셀 bbox·한국어 표 복원이 정확하다는 증거는 아니다. 기존 torch와 맞는 전체 dependency 해석은 미실행. `standard` 설치는 여러 문서/모델 의존성을 추가하므로 별도 추출 실험 환경에서 먼저 비교하고 성공한 최소 경로만 도입한다. |
| **6. Unstructured** | PDF `fast/hi_res/ocr_only`와 요소 유형, 페이지·좌표, 표 HTML을 제공한다. 요소 좌표와 모든 표 셀의 정확한 좌표는 동일 보장이 아니다. 지원 목록에 HWP/HWPX 전용 partitioner가 없다. [파티셔닝](https://docs.unstructured.io/open-source/core-functionality/partitioning), [메타데이터](https://docs.unstructured.io/open-source/concepts/document-elements) | 조회 버전 0.27.8, Python>=3.11,<3.14, Apache-2.0. PDF/이미지 경로에는 poppler·Tesseract 등 시스템 의존성과 추론 모델이 추가된다. 최신 inference 1.6.13의 torch>=2.10.0/onnxruntime>=1.25.0은 기존 값과 충돌. `pdf` extra가 Windows Python3.11에서 inference를 자동 포함하는 마커도 없다. [설치](https://docs.unstructured.io/open-source/installation/full-installation), [배포](https://pypi.org/pypi/unstructured/0.27.8/json), [inference](https://pypi.org/pypi/unstructured-inference/1.6.13/json) | **현 P0 보류.** 광범위 형식과 파이프라인이 필요할 때 유용하나 지금은 설치·의존성 비용이 크다. 위 마커는 ‘Windows에서 모든 기능 사용 불가’라는 뜻은 아니다. 클라우드 API의 기능·품질을 로컬 OSS 결과로 대신 주장하지 않는다. 모델 라이선스는 라이브러리 Apache-2.0과 별도로 확인한다. |
| **7. DeepDiff** | 중첩 Python 객체의 값·타입·추가/삭제와 경로를 비교한다. 문서 의미, 정정 관계, 법적 적용범위, KG 영향도를 자동 판정하는 도구가 아니다. [공식 저장소](https://github.com/qlustered/deepdiff), [순서 무시 옵션](https://zepworks.com/deepdiff/current/ignore_order.html) | 조회 버전 9.1.0, Python>=3.10, MIT. 모델·외부 프로그램 불필요. [배포](https://pypi.org/pypi/deepdiff/9.1.0/json), [라이선스](https://github.com/qlustered/deepdiff/blob/master/LICENSE) | **P0는 미추가.** 고정 ID별 dict 비교와 `difflib`로 먼저 처리한다. 중첩 구조 비교 코드가 반복될 때만 도입한다. 표 행을 무조건 `ignore_order=True`로 비교하면 순서와 대상 대응을 해석하는 제품 요구를 훼손할 수 있다. 변경 결과를 활성 지식에 자동 적용하지 않는다. |

## 한국어 OCR와 모델 비용

P0 PRD는 텍스트 PDF/HWPX를 대상으로 하며 구형 HWP·스캔 OCR 자동화는 범위 밖이다. **텍스트 PDF를 전부 OCR에 보내지 않는다.** OCR가 필요한 자료는 미지원/추출 실패로 남기거나 대응 텍스트 원본을 선택 등록한다.

- Docling 최신 문서는 RapidOCR의 `iso:ko`를 `korean` PP-OCR v5/v4 모델로 매핑한다. 빈 언어 목록은 `ch` 기본값이고 한 변환에서 첫 언어만 사용한다고 명시한다. 따라서 ‘OCR 켬’만으로 한국어 설정을 완료했다고 볼 수 없다. `ocrmac`을 공통 경로로 정하면 Windows 네이티브 조건을 충족하지 못한다. [공식 OCR 설정](https://docling-project.github.io/docling/concepts/OCR/)
- EasyOCR는 `ko`와 `korean_g2.pth` 한국어 모델을 제공하며, 선택 언어 가중치를 다운로드한다. CPU 모드가 있고 Windows에는 torch/torchvision 설치 안내가 별도로 있다. 코드 Apache-2.0과 개별 외부 모델의 출처·조건은 구분한다. [README](https://github.com/JaidedAI/EasyOCR), [한국어 모델 설정](https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/config.py)
- Tesseract 경로에는 한국어 `kor.traineddata`와 엔진 준비가 필요하다. `tessdata_fast` 가중치 저장소는 Apache-2.0을 선언한다. PyMuPDF 쪽도 언어 파일을 별도로 준비하는 방법을 설명한다. [공식 가중치](https://github.com/tesseract-ocr/tessdata_fast), [언어팩 안내](https://pymupdf.readthedocs.io/en/latest/ocr/tesseract-language-packs.html)
- **이 조사에서는 모델 파일을 다운로드하지 않았고 다운로드 총량·메모리·CPU 시간·한국어 OCR 정확도를 측정하지 않았다.** Docling/Unstructured/PyMuPDF의 서로 다른 모델 경로에 단일한 메모리 요구량이나 정확도 수치를 붙이지 않는다. 모델 파일을 사전에 로컬로 준비할 수 있다는 것과 다운로드 없이 바로 실행할 수 있다는 것은 다르다.

## FR-01·02·07에 적용할 최소 설계

아래는 라이브러리의 자동 제공 기능이 아니라 우리 어댑터가 책임져야 할 설계다.

1. **FR-01 등록:** 원본 bytes·URL·기관/공고 식별자·권리 상태·수집시점과 SHA-256을 보존한다. 해시는 파일 버전을 구분하고 중복 등록을 막는 데 사용한다. 파일 바이트가 달라졌다는 사실만으로 내용 변경 또는 공식 정정 관계가 입증되지는 않는다. 파서/버전/옵션도 기록하여 파서 교체에 따른 추출 차이와 원문 변경을 구분한다.
2. **FR-02 근거 위치:** `source_version_id + 물리 page index + bbox/좌표계 + 발췌문`을 PDF 근거로 저장한다. 인쇄 쪽수는 별도 필드이며 파서의 페이지 번호로 덮어쓰지 않는다. 표는 표 ID·행/열·병합 범위·원문 값을 유지한다. HWPX는 package part·구역·문단/표/셀 경로를 보존하고 `content.hpf`의 본문 순서를 따른다. XML 파일 이름 사전순과 `itertext()` 한 덩어리만으로 표/각주 위치를 대체하지 않는다. HWPX 경로는 원문 구조 위치이지 검증된 시각 페이지 좌표가 아니다.
3. **FR-07 변경 후보:** 공식 원공고/정정 ID로 버전 계열을 연결한 뒤 대응 절·표·공식 단지 코드 단위로 diff한다. `difflib.SequenceMatcher(..., autojunk=False)`는 반복 문장·셀을 임의의 빈번한 항목으로 취급하는 기본 휴리스틱을 끄는 선택이다. 그래도 최소 변경이나 의미 동일성을 보장하지는 않는다. 숫자·단위·부정·예외·조건은 정규화 과정에서 지우지 않는다. 같은 문서의 새 버전을 기존 버전에 덮어쓰지 않는다.
4. **영향은 별도 판단:** 문서 diff는 변경된 원문 후보를 만든다. 원문→사실→파생 지식의 저장된 근거 관계로 재검토 대상을 좁히고 사람이 결정한다. 단순 문자열 유사도를 공식 정정·법적 우선순위로 전환하지 않는다. 셀 병합·행 정렬을 복원하지 못한 결과는 빈 값/변경 없음으로 통과시키지 않는다.

## 도입 전에 필요한 최소 확인

대규모 파서 벤치마크 대신 기존 양산 정정 계열의 **실제 날짜 변경 위치와 단지별 표** 및 HWPX Q&A의 **문단/표 구조**를 원문과 대조한다. 우선 PDF 파서 하나만 확인하고 표가 필수인데 실패한 경우에 한하여 같은 페이지로 Docling과 비교한다. 확인 항목은 원문으로 다시 찾을 수 있는지, 숫자/단위/병합 셀의 대응이 맞는지, 정정 전후가 정확히 연결되는지다. 문서 지원 목록이나 저자 성능 주장을 이 결과로 대신하지 않는다.

이번 결과에는 설치 성공·전체 의존성 호환·Windows 실행·한국어 추출 정확도·처리시간 개선의 실측 증거가 없다. 현재 확정한 것은 공식 기능/라이선스 선언, 실제 프로젝트 미설치 상태, 명시된 일부 의존성 충돌과 재사용 후보의 범위다.
