# 교량편 QnA 시스템 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomm된 권장) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편」의 표(280여개)를 정규화 DB로 만들고, 그 위에 등급판정·전체등급산정·연도비교·본문검색 도구를 얹어 FastAPI+React QnA 시스템을 만든다.

**Architecture:** md 파일(KV 블록) → 파서 → SQLite(criteria/weight_tables/defect_score/text_docs) → 순수 함수 도구(grade_lookup/aggregate_*/compare_years/search_text) → FastAPI 엔드포인트 → LLM 도구호출(/chat) + React(채팅 탭 + 점검표 탭). 등급 확정·구간 비교는 전부 파이썬이 계산하고 LLM은 결과를 인용해 설명만 한다.

**Tech Stack:** Python 3.13 / FastAPI / sqlite3(표준 라이브러리) / scikit-learn(TF-IDF) / langchain-anthropic(도구호출) / React + TypeScript(Vite) / pytest

**Spec:** `docs/superpowers/specs/2026-08-31-교량편-qna-design.md`

## Global Constraints

- 모든 파서·계산 코드는 실제 데이터 파일(`data/안전점검진단_교량편/...`)에서 뽑아낸 원문 예시를 테스트 픽스처로 사용한다. 가짜 데이터로 테스트를 만들지 않는다.
- `search_text`는 스펙 6절의 "임베딩 검색" 대신 **TF-IDF+코사인유사도**로 구현한다 (기존 `QA/qna.py`가 이미 이 방식으로 검증됨, `scikit-learn`이 이미 의존성에 있어 무거운 임베딩 모델 의존성을 새로 들이지 않기 위한 실용적 대체 — 인터페이스(`search_text(query, section, year)`)는 스펙과 동일하게 유지해 나중에 교체 가능).
- 정성(qual) 기준은 절대 자동으로 등급을 확정하지 않는다 — 후보 목록과 근거만 반환한다 (design 6.2절).
- 정량 기준 중 여러 지표가 서로 다른 등급을 가리키면 **더 나쁜(낮은) 등급**을 채택한다 (design 6.2절, "최젓값 기준").
- DB 스키마는 스펙의 예시 SQL을 기반으로 하되, 등급 경계의 초과/이상 구분(`>` vs `>=`)을 정확히 표현하기 위해 `parsed_min_op`/`parsed_max_op` 컬럼을 추가한다 (스펙엔 없던 세부 보강, 정확성을 위해 필요).
- 파일 인코딩은 항상 UTF-8. Windows 콘솔 출력 시 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` 패턴을 유지한다(`QA/qna.py` 기존 관례).
- 1.7 보수·보강 공법 매핑, 공통편 통합은 이 계획의 범위 밖이다 (spec 3절).

---

## 파일 구조

```
backend/
  app/
    __init__.py
    parsing/
      __init__.py
      kv_blocks.py       # 표 md 파일(--- 구분) 공통 파서
      criteria.py         # 상태평가/안전성평가 기준 파서 (정량 정규식 포함)
      weights.py           # 표1.31/1.32 가중치 파서
      defect_score.py      # 표1.33 결함도점수 파서
      text_docs.py          # 1.1~1.7 본문(서술형) 파서
    db.py                # 스키마 생성 + 삽입 헬퍼
    build_db.py          # data/ 전체 순회 → DB 적재 (CLI 진입점)
    grading.py           # grade_lookup
    aggregate.py         # aggregate_structure_grade, aggregate_bridge_grade
    compare.py           # compare_years
    search.py            # TextSearcher (TF-IDF)
    llm_config.py        # api_key.txt 로딩 (QA/qna.py 로직 이식)
    llm_tools.py         # 도구 바인딩 + /chat 오케스트레이션
    main.py              # FastAPI 앱 + 엔드포인트
  tests/
    fixtures/            # 실제 데이터에서 발췌한 .md 조각
    test_kv_blocks.py
    test_criteria.py
    test_weights.py
    test_defect_score.py
    test_text_docs.py
    test_build_db.py
    test_grading.py
    test_aggregate.py
    test_compare.py
    test_search.py
    test_api.py
  requirements.txt
  data/                # build_db.py가 생성하는 bridge_qna.db (gitignore)

frontend/
  src/
    api.ts
    types.ts
    App.tsx
    components/
      ChatPanel.tsx
      InspectionSheet.tsx
```

---

### Task 1: KV 블록 공통 파서 (`kv_blocks.py`)

**Files:**
- Create: `backend/app/parsing/kv_blocks.py`
- Test: `backend/tests/test_kv_blocks.py`
- Create fixture: `backend/tests/fixtures/표1_11_콘크리트_바닥판.md` (아래 표1.11 2026 원문 그대로 복사)

**Interfaces:**
- Produces: `parse_kv_file(text: str) -> dict` — `{"meta": {...}, "blocks": [{"heading": str, key: [values...], ...}, ...]}`

- [ ] **Step 1: 픽스처 파일 생성**

`data/안전점검진단_교량편/1.4 상태평가기준 및 방법/table/2026/표1.11 콘크리트 바닥판 상태평가기준.md` 전체 내용을 그대로 `backend/tests/fixtures/표1_11_콘크리트_바닥판.md` 로 복사한다.

```bash
mkdir -p backend/tests/fixtures
cp "data/안전점검진단_교량편/1.4 상태평가기준 및 방법/table/2026/표1.11 콘크리트 바닥판 상태평가기준.md" "backend/tests/fixtures/표1_11_콘크리트_바닥판.md"
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# backend/tests/test_kv_blocks.py
from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file

FIXTURE = Path(__file__).parent / "fixtures" / "표1_11_콘크리트_바닥판.md"


def test_parses_meta_header():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    meta = parsed["meta"]
    assert meta["title"] == "[표 1.11] 콘크리트 바닥판 상태평가기준"
    assert meta["절"] == "1.4 상태평가기준 및 방법"
    assert meta["표"] == "1.11"
    assert meta["면"] == "29"
    assert meta["부재"] == "콘크리트 바닥판"
    assert meta["평가항목"] == [
        "균열1) > 1방향 균열",
        "균열1) > 2방향 균열",
        "열화 및 손상 > 누수 및 백태",
        "열화 및 손상 > 표면손상",
        "열화 및 손상 > 철근부식",
    ]


def test_parses_blocks_with_repeated_keys():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    blocks = parsed["blocks"]
    assert len(blocks) == 30  # 5항목 x 6등급(a~e, 단 e는 3개 항목만 서술형... 실제로는 30개, Step4에서 실측 확정
    b_1방향 = next(
        b for b in blocks
        if b.get("등급") == ["b"] and b.get("세부항목") == ["1방향 균열"]
    )
    assert b_1방향["기준"] == [
        "균열폭 0.1㎜이상～0.3㎜미만",
        "균열률 2%미만",
    ]
    assert b_1방향["출처"] == ["[표 1.11] 안전점검진단_교량@2026 29면"]
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_kv_blocks.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.parsing.kv_blocks'`

- [ ] **Step 4: `blocks` 개수를 실측으로 확정**

구현 전에 실제 파일의 블록 개수를 세어 테스트의 매직넘버를 정확한 값으로 고정한다.

```bash
python3 -c "
text = open('backend/tests/fixtures/표1_11_콘크리트_바닥판.md', encoding='utf-8').read()
segments = [[]]
for line in text.splitlines():
    if line.strip() == '---':
        segments.append([])
    else:
        segments[-1].append(line)
print(len([s for s in segments if any(l.strip() for l in s)]) - 1)  # 헤더 제외
"
```
나온 숫자로 `test_parses_blocks_with_repeated_keys`의 `len(blocks) == N` 값을 갱신한다.

- [ ] **Step 5: 최소 구현 작성**

```python
# backend/app/parsing/kv_blocks.py
"""`---`로 구분된 KV 마크다운 표 파일을 {meta, blocks} 구조로 파싱한다."""
from __future__ import annotations


def parse_kv_file(text: str) -> dict:
    lines = text.splitlines()
    segments: list[list[str]] = [[]]
    for line in lines:
        if line.strip() == "---":
            segments.append([])
        else:
            segments[-1].append(line)
    segments = ["\n".join(seg).strip() for seg in segments]
    segments = [s for s in segments if s]
    if not segments:
        return {"meta": {}, "blocks": []}
    header_text, *block_texts = segments
    return {
        "meta": _parse_meta(header_text),
        "blocks": [_parse_block(bt) for bt in block_texts],
    }


def _parse_meta(text: str) -> dict:
    lines = text.splitlines()
    meta: dict = {}
    if lines and lines[0].lstrip().startswith("#"):
        meta["title"] = lines[0].lstrip("#").strip()
        lines = lines[1:]

    current_list_key: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            if current_list_key:
                meta.setdefault(current_list_key, []).append(line[2:].strip())
            continue
        if line.endswith(":"):
            current_list_key = line[:-1].strip()
            meta[current_list_key] = []
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
            current_list_key = None
    return meta


def _parse_block(text: str) -> dict:
    lines = text.splitlines()
    data: dict = {}
    if lines and lines[0].lstrip().startswith("#"):
        data["heading"] = lines[0].lstrip("#").strip()
        lines = lines[1:]
    for raw in lines:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data.setdefault(key.strip(), []).append(value.strip())
    return data
```

- [ ] **Step 6: 테스트 실행해서 통과 확인**

```bash
cd backend && python -m pytest tests/test_kv_blocks.py -v
```
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add backend/app/parsing/kv_blocks.py backend/tests/test_kv_blocks.py backend/tests/fixtures/표1_11_콘크리트_바닥판.md
git commit -m "feat: KV 블록 공통 파서 추가"
```

---

### Task 2: 정량 기준 정규식 파서 + criteria 빌더 (`criteria.py`)

**Files:**
- Create: `backend/app/parsing/criteria.py`
- Test: `backend/tests/test_criteria.py`

**Interfaces:**
- Consumes: `parse_kv_file` (Task 1) — `dict` with `meta`/`blocks`
- Produces:
  - `parse_criterion_text(text: str) -> ParsedCriterion | None`
  - `ParsedCriterion` dataclass: `field: str | None, min_value: float | None, min_op: str | None, max_value: float | None, max_op: str | None, unit: str | None`
  - `build_criteria_rows(parsed: dict, year: int, section: str, source_path: str) -> list[dict]` — 각 dict는 `year, section, table_no, table_title, member, item, subitem, grade, criterion_raw, criterion_type, parsed_field, parsed_min, parsed_min_op, parsed_max, parsed_max_op, parsed_unit, page, source_path` 키를 가짐

- [ ] **Step 1: 실패하는 테스트 작성 — 정량 파서 단위테스트**

실제 표1.11/표1.34 원문에서 뽑은 문장들로 테스트한다.

```python
# backend/tests/test_criteria.py
from app.parsing.criteria import parse_criterion_text


def test_parses_range_with_unit():
    r = parse_criterion_text("균열폭 0.3㎜이상～0.5㎜미만")
    assert r is not None
    assert r.field == "균열폭"
    assert r.min_value == 0.3 and r.min_op == ">="
    assert r.max_value == 0.5 and r.max_op == "<"
    assert r.unit == "㎜"


def test_parses_percent_range_with_space_before_unit():
    r = parse_criterion_text("균열률 2%이상～10% 미만")
    assert r.field == "균열률"
    assert r.min_value == 2 and r.min_op == ">="
    assert r.max_value == 10 and r.max_op == "<"
    assert r.unit == "%"


def test_parses_lower_bound_only():
    r = parse_criterion_text("균열폭 1.0㎜이상")
    assert r.field == "균열폭"
    assert r.min_value == 1.0 and r.min_op == ">="
    assert r.max_value is None


def test_parses_upper_bound_only():
    r = parse_criterion_text("균열폭 0.1㎜미만")
    assert r.field == "균열폭"
    assert r.max_value == 0.1 and r.max_op == "<"
    assert r.min_value is None


def test_parses_safety_factor_range():
    r = parse_criterion_text("0.9 ≤ SF < 1 이나, 공용내하력이 설계하중보다 크게 평가된 경우")
    assert r.field == "SF"
    assert r.min_value == 0.9 and r.min_op == ">="
    assert r.max_value == 1 and r.max_op == "<"


def test_parses_safety_factor_gt():
    r = parse_criterion_text("SF > 1.0")
    assert r.field == "SF"
    assert r.min_value == 1.0 and r.min_op == ">"
    assert r.max_value is None


def test_fraction_denominator_is_not_mistaken_for_threshold():
    # "1/2 이상"의 2를 "2 이상"으로 잘못 읽으면 안 된다 — 실제 표1.22 교량받침 e등급 원문
    r = parse_criterion_text("받침이 밀착되지 않고 떠있는 부분이 전체면적의 1/2 이상")
    assert r is None  # 정성 항목으로 폴백


def test_pure_qualitative_text_returns_none():
    r = parse_criterion_text("부식으로 인한 철근의 단면감소가 심하여 바닥판의 안전성이 저하되는 경우")
    assert r is None


def test_none_and_dash_are_not_quant():
    assert parse_criterion_text("없음") is None
    assert parse_criterion_text("-") is None
```

- [ ] **Step 2: 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_criteria.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 정량 파서 구현**

```python
# backend/app/parsing/criteria.py
"""상태평가/안전성평가 기준(criteria) 표를 정규화된 행으로 변환한다.

기준 문장은 두 갈래다:
  - 정량(quant): "균열폭 0.3㎜이상～0.5㎜미만", "SF > 1.0" 처럼 숫자 구간이 있는 문장.
  - 정성(qual): "펀칭파괴 발생 가능성 있음"처럼 점검자 판단이 필요한 서술.
1.4절 본문("정량적 평가와 정성적 평가를 동시에 수행하며 최젓값을 기준으로 산정")에 따라
정량은 코드가 확정하고, 정성은 절대 자동 확정하지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedCriterion:
    field: str | None
    min_value: float | None
    min_op: str | None
    max_value: float | None
    max_op: str | None
    unit: str | None


_UNIT = r"㎜|mm|%|kg/m3|kg|kN|m3"
_NUM = r"(?<!/)[0-9]+(?:\.[0-9]+)?"

_RANGE_PATTERN = re.compile(
    rf"(?P<min>{_NUM})\s*(?P<unit1>{_UNIT})?\s*이상\s*[～~]\s*"
    rf"(?P<max>{_NUM})\s*(?P<unit2>{_UNIT})?\s*미만"
)
_GE_PATTERN = re.compile(rf"(?P<val>{_NUM})\s*(?P<unit>{_UNIT})?\s*이상(?!\s*[～~])")
_LT_PATTERN = re.compile(rf"(?P<val>{_NUM})\s*(?P<unit>{_UNIT})?\s*미만")
_FIELD_PREFIX = re.compile(r"^([^\d]+?)\s*[0-9]")

_SF_RANGE_PATTERN = re.compile(
    rf"(?P<min>{_NUM})\s*(?P<minop>[≤<])\s*SF\s*(?P<maxop><)\s*(?P<max>{_NUM})"
)
_SF_CMP_PATTERN = re.compile(rf"SF\s*(?P<op>[>≥])\s*(?P<val>{_NUM})")
_SF_OP_MAP = {"≤": ">=", "≥": ">=", "<": "<", ">": ">"}


def parse_criterion_text(text: str) -> ParsedCriterion | None:
    text = text.strip()
    if text in ("", "없음", "-"):
        return None

    m = _SF_RANGE_PATTERN.search(text)
    if m:
        return ParsedCriterion(
            field="SF",
            min_value=float(m.group("min")),
            min_op=_SF_OP_MAP[m.group("minop")],
            max_value=float(m.group("max")),
            max_op="<",
            unit=None,
        )

    m = _SF_CMP_PATTERN.search(text)
    if m:
        return ParsedCriterion(
            field="SF",
            min_value=float(m.group("val")),
            min_op=_SF_OP_MAP[m.group("op")],
            max_value=None,
            max_op=None,
            unit=None,
        )

    field_match = _FIELD_PREFIX.match(text)
    field = field_match.group(1).strip() if field_match else None

    m = _RANGE_PATTERN.search(text)
    if m:
        unit = m.group("unit1") or m.group("unit2")
        return ParsedCriterion(field, float(m.group("min")), ">=", float(m.group("max")), "<", unit)

    m = _GE_PATTERN.search(text)
    if m:
        return ParsedCriterion(field, float(m.group("val")), ">=", None, None, m.group("unit"))

    m = _LT_PATTERN.search(text)
    if m:
        return ParsedCriterion(field, None, None, float(m.group("val")), "<", m.group("unit"))

    return None


def classify_criterion(text: str) -> str:
    text = text.strip()
    if text in ("", "없음", "-"):
        return "none"
    return "quant" if parse_criterion_text(text) is not None else "qual"


def build_criteria_rows(parsed: dict, year: int, section: str, source_path: str) -> list[dict]:
    meta = parsed["meta"]
    table_no = meta.get("표")
    table_title = meta.get("title")
    page_raw = meta.get("면")
    page = int(page_raw) if page_raw and page_raw.isdigit() else None

    rows: list[dict] = []
    for block in parsed["blocks"]:
        member = (block.get("부재") or [meta.get("부재")])[0]
        item = (block.get("평가항목") or [None])[0]
        subitem = (block.get("세부항목") or [""])[0]
        grade = (block.get("등급") or [None])[0]
        for raw_text in block.get("기준", []):
            criterion_type = classify_criterion(raw_text)
            parsed_criterion = parse_criterion_text(raw_text) if criterion_type == "quant" else None
            rows.append({
                "year": year,
                "section": section,
                "table_no": table_no,
                "table_title": table_title,
                "member": member,
                "item": item,
                "subitem": subitem,
                "grade": grade,
                "criterion_raw": raw_text,
                "criterion_type": criterion_type,
                "parsed_field": parsed_criterion.field if parsed_criterion else None,
                "parsed_min": parsed_criterion.min_value if parsed_criterion else None,
                "parsed_min_op": parsed_criterion.min_op if parsed_criterion else None,
                "parsed_max": parsed_criterion.max_value if parsed_criterion else None,
                "parsed_max_op": parsed_criterion.max_op if parsed_criterion else None,
                "parsed_unit": parsed_criterion.unit if parsed_criterion else None,
                "page": page,
                "source_path": source_path,
            })
    return rows
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

```bash
cd backend && python -m pytest tests/test_criteria.py -v
```
Expected: PASS (9 tests)

- [ ] **Step 5: `build_criteria_rows` 통합 테스트 추가 (Task 1 픽스처 재사용)**

```python
# backend/tests/test_criteria.py 에 추가
from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.criteria import build_criteria_rows

FIXTURE = Path(__file__).parent / "fixtures" / "표1_11_콘크리트_바닥판.md"


def test_build_criteria_rows_from_real_table():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    rows = build_criteria_rows(parsed, year=2026, section="1.4 상태평가기준 및 방법", source_path=str(FIXTURE))

    b_rows = [r for r in rows if r["grade"] == "b" and r["subitem"] == "1방향 균열"]
    assert len(b_rows) == 2  # 균열폭 기준 + 균열률 기준, OR 관계로 행 분리
    assert {r["criterion_raw"] for r in b_rows} == {
        "균열폭 0.1㎜이상～0.3㎜미만",
        "균열률 2%미만",
    }
    assert all(r["criterion_type"] == "quant" for r in b_rows)
    assert all(r["member"] == "콘크리트 바닥판" for r in rows)

    e_철근부식 = next(
        r for r in rows if r["grade"] == "e" and r["subitem"] == "철근부식"
    )
    assert e_철근부식["criterion_type"] == "qual"
    assert e_철근부식["parsed_min"] is None
```

- [ ] **Step 6: 테스트 실행 후 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_criteria.py -v
git add backend/app/parsing/criteria.py backend/tests/test_criteria.py
git commit -m "feat: 정량 기준 정규식 파서 및 criteria 행 빌더 추가"
```

---

### Task 3: 가중치표·결함도점수표 파서 (`weights.py`, `defect_score.py`)

**Files:**
- Create: `backend/app/parsing/weights.py`
- Create: `backend/app/parsing/defect_score.py`
- Test: `backend/tests/test_weights.py`, `backend/tests/test_defect_score.py`
- Fixtures: `backend/tests/fixtures/표1_31_일반교량_가중치.md`, `backend/tests/fixtures/표1_33_결함도점수.md`

**Interfaces:**
- Consumes: `parse_kv_file` (Task 1)
- Produces:
  - `parse_weight_table(parsed: dict, year: int, source_path: str) -> list[dict]` — `{year, category, defect_item, structure_type, weight, source_path}`
  - `parse_defect_score(parsed: dict, year: int, source_path: str) -> list[dict]` — `{year, grade, index_value, range_min, range_max, source_path}`

- [ ] **Step 1: 픽스처 복사**

```bash
cp "data/안전점검진단_교량편/1.4 상태평가기준 및 방법/table/2026/표1.31 구조형식에 따른 일반교량의 부재별 가중치.md" "backend/tests/fixtures/표1_31_일반교량_가중치.md"
cp "data/안전점검진단_교량편/1.4 상태평가기준 및 방법/table/2026/표1.33 결함도 점수 범위에 따른 기준.md" "backend/tests/fixtures/표1_33_결함도점수.md"
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# backend/tests/test_weights.py
from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.weights import parse_weight_table

FIXTURE = Path(__file__).parent / "fixtures" / "표1_31_일반교량_가중치.md"


def test_parses_weight_matrix_and_skips_total_row():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_weight_table(parsed, year=2026, source_path=str(FIXTURE))

    assert not any(r["category"] == "합계" for r in rows)

    바닥판_일반거더 = next(
        r for r in rows
        if r["defect_item"] == "바닥판" and r["structure_type"] == "거더교량 > 일반 거더교 > 일반"
    )
    assert 바닥판_일반거더["weight"] == 18.0
    assert 바닥판_일반거더["category"] == "상부"

    바닥판_바닥판없음 = next(
        r for r in rows
        if r["defect_item"] == "바닥판" and r["structure_type"] == "거더교량 > 일반 거더교 > 바닥판 없음"
    )
    assert 바닥판_바닥판없음["weight"] is None  # 원문 '-'

    일반거더_전체가중치 = sum(
        r["weight"] for r in rows
        if r["structure_type"] == "거더교량 > 일반 거더교 > 일반" and r["weight"] is not None
    )
    assert 일반거더_전체가중치 == 117.0  # 표의 '합계' 행 값과 일치해야 함
```

```python
# backend/tests/test_defect_score.py
from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.defect_score import parse_defect_score

FIXTURE = Path(__file__).parent / "fixtures" / "표1_33_결함도점수.md"


def test_parses_index_and_range_for_each_grade():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    rows = {r["grade"]: r for r in parse_defect_score(parsed, year=2026, source_path=str(FIXTURE))}

    assert rows["A"]["index_value"] == 0.10
    assert rows["A"]["range_min"] == 0.0 and rows["A"]["range_max"] == 0.13

    assert rows["E"]["index_value"] == 1.00
    assert rows["E"]["range_min"] == 0.79 and rows["E"]["range_max"] is None
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_weights.py tests/test_defect_score.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: `weights.py` 구현**

```python
# backend/app/parsing/weights.py
"""표1.31/1.32(구조형식별 부재 가중치) 파서. 각 블록은 '구분'(상부/하부/받침/기타/재료시험)과
'결함도 평가항목'(바닥판/주형/...) 행 하나이며, 그 외 키는 구조형식 경로 -> 가중치 값이다."""
from __future__ import annotations

_META_KEYS = {"heading", "구분", "결함도 평가항목", "출처"}


def parse_weight_table(parsed: dict, year: int, source_path: str) -> list[dict]:
    rows: list[dict] = []
    for block in parsed["blocks"]:
        category = (block.get("구분") or [None])[0]
        if category == "합계":
            continue
        defect_item = (block.get("결함도 평가항목") or [None])[0]
        for key, values in block.items():
            if key in _META_KEYS:
                continue
            raw = values[0].strip()
            weight = None if raw == "-" else float(raw)
            rows.append({
                "year": year,
                "category": category,
                "defect_item": defect_item,
                "structure_type": key,
                "weight": weight,
                "source_path": source_path,
            })
    return rows
```

- [ ] **Step 5: `defect_score.py` 구현**

```python
# backend/app/parsing/defect_score.py
"""표1.33(결함도 점수 범위에 따른 기준) 파서.
블록 두 개('결함도 지수', '결함도 범위')를 등급(A~E)별 한 행으로 합친다."""
from __future__ import annotations

import re

_GRADES = ("A", "B", "C", "D", "E")
_RANGE_BOTH = re.compile(r"^([0-9.]+)≤X＜([0-9.]+)$")
_RANGE_LOWER_ONLY = re.compile(r"^([0-9.]+)≤X$")


def _parse_range(text: str) -> tuple[float, float | None]:
    m = _RANGE_BOTH.match(text.strip())
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _RANGE_LOWER_ONLY.match(text.strip())
    if m:
        return float(m.group(1)), None
    raise ValueError(f"결함도 범위 문자열을 해석할 수 없습니다: {text!r}")


def parse_defect_score(parsed: dict, year: int, source_path: str) -> list[dict]:
    index_values: dict[str, float] = {}
    ranges: dict[str, tuple[float, float | None]] = {}

    for block in parsed["blocks"]:
        label = (block.get("기준") or [None])[0]
        if label == "결함도 지수":
            for g in _GRADES:
                if g in block:
                    index_values[g] = float(block[g][0])
        elif label == "결함도 범위":
            for g in _GRADES:
                if g in block:
                    ranges[g] = _parse_range(block[g][0])

    rows = []
    for g in _GRADES:
        lo, hi = ranges.get(g, (None, None))
        rows.append({
            "year": year,
            "grade": g,
            "index_value": index_values.get(g),
            "range_min": lo,
            "range_max": hi,
            "source_path": source_path,
        })
    return rows
```

- [ ] **Step 6: 테스트 실행해서 통과 확인**

```bash
cd backend && python -m pytest tests/test_weights.py tests/test_defect_score.py -v
```
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add backend/app/parsing/weights.py backend/app/parsing/defect_score.py backend/tests/test_weights.py backend/tests/test_defect_score.py backend/tests/fixtures/표1_31_일반교량_가중치.md backend/tests/fixtures/표1_33_결함도점수.md
git commit -m "feat: 가중치표/결함도점수표 파서 추가"
```

---

### Task 4: 본문(서술형) 파서 (`text_docs.py`)

**Files:**
- Create: `backend/app/parsing/text_docs.py`
- Test: `backend/tests/test_text_docs.py`
- Fixture: `backend/tests/fixtures/1_1_관리일반.md`

**Interfaces:**
- Produces: `parse_text_file(text: str) -> dict` — `{"meta": {"title":..., "문서":..., "판본":..., "절":...}, "paragraphs": [{"heading_path": str, "content": str}, ...]}`

표 파일과 달리 본문 파일은 `---` 구분자가 없고 `#`/`##`/`###` 마크다운 헤딩만 있다 — Task 1의 `kv_blocks.py`를 재사용하지 않고 별도 파서를 만든다.

- [ ] **Step 1: 픽스처 복사**

```bash
cp "data/안전점검진단_교량편/1.1 관리일반/text/2026/1.1 관리일반.md" "backend/tests/fixtures/1_1_관리일반.md"
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# backend/tests/test_text_docs.py
from pathlib import Path
from app.parsing.text_docs import parse_text_file

FIXTURE = Path(__file__).parent / "fixtures" / "1_1_관리일반.md"


def test_parses_meta():
    parsed = parse_text_file(FIXTURE.read_text(encoding="utf-8"))
    assert parsed["meta"]["title"] == "1.1 관리일반"
    assert parsed["meta"]["절"] == "1.1"
    assert parsed["meta"]["판본"] == "안전점검진단_교량@2026"


def test_paragraphs_are_grouped_by_heading_path():
    parsed = parse_text_file(FIXTURE.read_text(encoding="utf-8"))
    paragraphs = parsed["paragraphs"]

    적용범위_문단 = [p for p in paragraphs if p["heading_path"] == "1.1.1 적용 범위"]
    assert len(적용범위_문단) >= 2
    assert any("도로교량과 철도교량에 적용" in p["content"] for p in 적용범위_문단)

    용어정의_문단 = [p for p in paragraphs if p["heading_path"] == "1.1.2 용어 정의"]
    assert any("특수교(特殊橋)" in p["content"] for p in 용어정의_문단)


def test_table_reference_lines_are_skipped():
    parsed = parse_text_file(FIXTURE.read_text(encoding="utf-8"))
    assert not any("표참조" in p["content"] for p in parsed["paragraphs"])
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_text_docs.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: 구현**

```python
# backend/app/parsing/text_docs.py
"""1.1~1.7절 서술형 본문(text/*.md) 파서. 표와 달리 '---' 구분자가 없고
'#'/'##'/'###' 마크다운 헤딩 계층만 있어 kv_blocks.py와는 별개로 구현한다."""
from __future__ import annotations

import re

_HEADING_PATTERN = re.compile(r"^(#{2,6})\s+(.*)$")
_META_KEY_PATTERN = re.compile(r"^(문서|판본|절):\s*(.*)$")


def parse_text_file(text: str) -> dict:
    meta: dict = {}
    heading_stack: list[tuple[int, str]] = []
    paragraphs: list[dict] = []
    current_content: list[str] = []
    title_captured = False
    meta_done = False

    def flush() -> None:
        if not current_content:
            return
        heading_path = " > ".join(h[1] for h in heading_stack)
        for content in current_content:
            paragraphs.append({"heading_path": heading_path, "content": content})
        current_content.clear()

    for raw in text.splitlines():
        stripped = raw.strip()

        if not title_captured and stripped.startswith("# "):
            meta["title"] = stripped[2:].strip()
            title_captured = True
            continue

        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            flush()
            meta_done = True
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_stack = [h for h in heading_stack if h[0] < level]
            heading_stack.append((level, title))
            continue

        if not meta_done:
            meta_match = _META_KEY_PATTERN.match(stripped)
            if meta_match:
                meta[meta_match.group(1)] = meta_match.group(2).strip()
                continue

        if stripped.startswith("내용:"):
            current_content.append(stripped[len("내용:"):].strip())
        # 표참조/그림참조 줄은 criteria/weights 파서가 담당하므로 여기서는 건너뛴다.

    flush()
    return {"meta": meta, "paragraphs": paragraphs}
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

```bash
cd backend && python -m pytest tests/test_text_docs.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add backend/app/parsing/text_docs.py backend/tests/test_text_docs.py backend/tests/fixtures/1_1_관리일반.md
git commit -m "feat: 서술형 본문 파서 추가"
```

---

### Task 5: DB 스키마 + 전체 빌드 스크립트 (`db.py`, `build_db.py`)

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/build_db.py`
- Test: `backend/tests/test_build_db.py`

**Interfaces:**
- Consumes: Task 1~4의 모든 파서 함수
- Produces:
  - `init_db(path: str) -> sqlite3.Connection`
  - `insert_criteria/insert_weight/insert_defect_score/insert_text_docs(conn, rows: list[dict]) -> None`
  - `build_db.main(data_dir: Path, db_path: Path) -> dict` (반환값: `{"criteria": N, "weight_tables": N, "defect_score": N, "text_docs": N, "skipped": [paths...]}`, 이후 Task 6~9가 이 DB 파일을 그대로 사용)

- [ ] **Step 1: 스키마 구현**

```python
# backend/app/db.py
"""SQLite 스키마 생성 및 삽입 헬퍼."""
from __future__ import annotations

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS criteria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  section TEXT NOT NULL,
  table_no TEXT,
  table_title TEXT,
  member TEXT NOT NULL,
  item TEXT NOT NULL,
  subitem TEXT,
  grade TEXT NOT NULL,
  criterion_raw TEXT NOT NULL,
  criterion_type TEXT NOT NULL,
  parsed_field TEXT,
  parsed_min REAL,
  parsed_min_op TEXT,
  parsed_max REAL,
  parsed_max_op TEXT,
  parsed_unit TEXT,
  page INTEGER,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_criteria_lookup ON criteria (year, member, item, subitem);

CREATE TABLE IF NOT EXISTS weight_tables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  category TEXT,
  defect_item TEXT NOT NULL,
  structure_type TEXT NOT NULL,
  weight REAL,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weight_lookup ON weight_tables (year, defect_item, structure_type);

CREATE TABLE IF NOT EXISTS defect_score (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  grade TEXT NOT NULL,
  index_value REAL,
  range_min REAL,
  range_max REAL,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_defect_score_lookup ON defect_score (year, grade);

CREATE TABLE IF NOT EXISTS text_docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  section TEXT,
  heading_path TEXT,
  paragraph TEXT NOT NULL,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_docs_lookup ON text_docs (year, section);
"""


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def insert_criteria(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO criteria
           (year, section, table_no, table_title, member, item, subitem, grade,
            criterion_raw, criterion_type, parsed_field, parsed_min, parsed_min_op,
            parsed_max, parsed_max_op, parsed_unit, page, source_path)
           VALUES (:year, :section, :table_no, :table_title, :member, :item, :subitem, :grade,
                   :criterion_raw, :criterion_type, :parsed_field, :parsed_min, :parsed_min_op,
                   :parsed_max, :parsed_max_op, :parsed_unit, :page, :source_path)""",
        rows,
    )
    conn.commit()


def insert_weight(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO weight_tables (year, category, defect_item, structure_type, weight, source_path)
           VALUES (:year, :category, :defect_item, :structure_type, :weight, :source_path)""",
        rows,
    )
    conn.commit()


def insert_defect_score(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO defect_score (year, grade, index_value, range_min, range_max, source_path)
           VALUES (:year, :grade, :index_value, :range_min, :range_max, :source_path)""",
        rows,
    )
    conn.commit()


def insert_text_docs(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO text_docs (year, section, heading_path, paragraph, source_path)
           VALUES (:year, :section, :heading_path, :paragraph, :source_path)""",
        rows,
    )
    conn.commit()
```

- [ ] **Step 2: 실패하는 테스트 작성 (실제 `data/` 폴더 전체를 대상으로)**

```python
# backend/tests/test_build_db.py
import sqlite3
from pathlib import Path

from app.build_db import main as build_main

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


def test_build_db_populates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    stats = build_main(DATA_DIR, db_path)

    assert stats["criteria"] > 0
    assert stats["weight_tables"] > 0
    assert stats["defect_score"] > 0
    assert stats["text_docs"] > 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 실제 데이터 사실 검증: 콘크리트 바닥판 2026, c등급 1방향균열 2개 기준(균열폭/균열률)
    rows = conn.execute(
        "SELECT criterion_raw FROM criteria WHERE year=2026 AND member='콘크리트 바닥판' "
        "AND subitem='1방향 균열' AND grade='c'"
    ).fetchall()
    assert {r["criterion_raw"] for r in rows} == {
        "균열폭 0.3㎜이상～0.5㎜미만",
        "균열률 2%이상～10% 미만",
    }

    # 실제 사실: 월류(여유고 조사)는 2026에만 존재, 2024엔 없음
    count_2026 = conn.execute(
        "SELECT COUNT(*) c FROM criteria WHERE year=2026 AND member='월류(여유고 조사)'"
    ).fetchone()["c"]
    count_2024 = conn.execute(
        "SELECT COUNT(*) c FROM criteria WHERE year=2024 AND member='월류(여유고 조사)'"
    ).fetchone()["c"]
    assert count_2026 > 0
    assert count_2024 == 0

    # 실제 사실: 표1.31 일반거더교 일반 형식의 가중치 합계는 117
    total = conn.execute(
        "SELECT SUM(weight) t FROM weight_tables WHERE year=2026 "
        "AND structure_type='거더교량 > 일반 거더교 > 일반'"
    ).fetchone()["t"]
    assert total == 117.0
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_build_db.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: 구현**

```python
# backend/app/build_db.py
"""data/안전점검진단_교량편 전체를 순회해 SQLite로 적재하는 CLI 진입점."""
from __future__ import annotations

import sys
from pathlib import Path

from app.db import init_db, insert_criteria, insert_defect_score, insert_text_docs, insert_weight
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.criteria import build_criteria_rows
from app.parsing.weights import parse_weight_table
from app.parsing.defect_score import parse_defect_score
from app.parsing.text_docs import parse_text_file


def _classify_table_file(parsed: dict) -> str:
    blocks = parsed["blocks"]
    if not blocks:
        return "empty"
    first = blocks[0]
    if "등급" in first:
        return "criteria"
    label = (first.get("기준") or [None])[0]
    if label in ("결함도 지수", "결함도 범위"):
        return "defect_score"
    if "구분" in first and "결함도 평가항목" in first:
        return "weight"
    return "other"


def main(data_dir: Path, db_path: Path) -> dict:
    conn = init_db(str(db_path))
    stats = {"criteria": 0, "weight_tables": 0, "defect_score": 0, "text_docs": 0, "skipped": []}

    for section_dir in sorted(data_dir.iterdir()):
        if not section_dir.is_dir():
            continue
        section = section_dir.name

        table_dir = section_dir / "table"
        if table_dir.exists():
            for year_dir in sorted(table_dir.iterdir()):
                if not year_dir.is_dir():
                    continue
                year = int(year_dir.name)
                for md_file in sorted(year_dir.glob("*.md")):
                    parsed = parse_kv_file(md_file.read_text(encoding="utf-8"))
                    kind = _classify_table_file(parsed)
                    if kind == "criteria":
                        rows = build_criteria_rows(parsed, year, section, str(md_file))
                        if rows:
                            insert_criteria(conn, rows)
                            stats["criteria"] += len(rows)
                    elif kind == "defect_score":
                        rows = parse_defect_score(parsed, year, str(md_file))
                        insert_defect_score(conn, rows)
                        stats["defect_score"] += len(rows)
                    elif kind == "weight":
                        rows = parse_weight_table(parsed, year, str(md_file))
                        insert_weight(conn, rows)
                        stats["weight_tables"] += len(rows)
                    else:
                        stats["skipped"].append(str(md_file))

        text_dir = section_dir / "text"
        if text_dir.exists():
            for year_dir in sorted(text_dir.iterdir()):
                if not year_dir.is_dir():
                    continue
                year = int(year_dir.name)
                for md_file in sorted(year_dir.glob("*.md")):
                    parsed = parse_text_file(md_file.read_text(encoding="utf-8"))
                    rows = [
                        {
                            "year": year,
                            "section": section,
                            "heading_path": p["heading_path"],
                            "paragraph": p["content"],
                            "source_path": str(md_file),
                        }
                        for p in parsed["paragraphs"]
                    ]
                    if rows:
                        insert_text_docs(conn, rows)
                        stats["text_docs"] += len(rows)

    conn.close()
    return stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data" / "안전점검진단_교량편"
    db_path = Path(__file__).resolve().parent.parent / "data" / "bridge_qna.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    result = main(data_dir, db_path)
    print(f"criteria={result['criteria']} weight_tables={result['weight_tables']} "
          f"defect_score={result['defect_score']} text_docs={result['text_docs']} "
          f"skipped={len(result['skipped'])}개 파일")
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

```bash
cd backend && python -m pytest tests/test_build_db.py -v
```
Expected: PASS. 실패하면 `stats["skipped"]`를 출력해 어떤 표 형식이 아직 분류되지 않았는지 확인하고 `_classify_table_file`을 보강한다(예: `표_콘크리트 바닥판.md` 같은 1.2절 현장조사 손상종류 표는 `"other"`로 스킵되는 게 정상 — 이 계획의 범위 밖).

- [ ] **Step 6: 실제 DB 파일 생성 (백엔드 실행에 필요)**

```bash
cd backend && python -m app.build_db
```
콘솔에 `criteria=NNNN weight_tables=NNN defect_score=20 text_docs=NNNN skipped=NN개 파일` 출력 확인.

- [ ] **Step 7: 커밋**

```bash
git add backend/app/db.py backend/app/build_db.py backend/tests/test_build_db.py
git commit -m "feat: SQLite 스키마 및 전체 빌드 스크립트 추가"
```
(`backend/data/bridge_qna.db`는 `.gitignore`에 추가해 커밋하지 않는다 — Task 5에서 `.gitignore`도 함께 생성)

```bash
echo "backend/data/*.db" >> .gitignore
git add .gitignore
git commit -m "chore: 빌드 산출물 DB 파일 gitignore 추가"
```

---

### Task 6: `grade_lookup` — 부재 등급 판정

**Files:**
- Create: `backend/app/grading.py`
- Test: `backend/tests/test_grading.py`

**Interfaces:**
- Consumes: Task 5가 만든 `criteria` 테이블(sqlite3.Connection 통해 접근)
- Produces: `grade_lookup(conn, member: str, item: str, subitem: str | None, measures: dict[str, float], year: int = 2026) -> dict`
  - 반환 형태: `{"status": "graded", "grade": "c", "evidence": [...]}` 또는 `{"status": "needs_judgment", "candidates": [...]}` 또는 `{"status": "no_match", ...}` 또는 `{"status": "not_found"}`

- [ ] **Step 1: 실패하는 테스트 작성 (실제 build_db 결과를 fixture DB로 사용)**

```python
# backend/tests/test_grading.py
import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.grading import grade_lookup

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_grades_quant_criterion_within_c_range(conn):
    result = grade_lookup(
        conn, member="콘크리트 바닥판", item="균열1)", subitem="1방향 균열",
        measures={"균열폭": 0.35}, year=2026,
    )
    assert result["status"] == "graded"
    assert result["grade"] == "c"
    assert any("0.3㎜이상～0.5㎜미만" in e["criterion_raw"] for e in result["evidence"])


def test_takes_worse_grade_when_multiple_indicators_disagree(conn):
    # 균열폭은 b 구간(0.1~0.3), 균열률은 d 구간(10~20%) -> 더 나쁜 d 채택
    result = grade_lookup(
        conn, member="콘크리트 바닥판", item="균열1)", subitem="1방향 균열",
        measures={"균열폭": 0.2, "균열률": 15}, year=2026,
    )
    assert result["status"] == "graded"
    assert result["grade"] == "d"


def test_returns_needs_judgment_for_qualitative_only_item(conn):
    result = grade_lookup(
        conn, member="콘크리트 바닥판", item="열화 및 손상", subitem="철근부식",
        measures={}, year=2026,
    )
    assert result["status"] == "needs_judgment"
    grades = {c["grade"] for c in result["candidates"]}
    assert "e" in grades
    assert any("단면감소가 심하여" in c["criterion_raw"] for c in result["candidates"] if c["grade"] == "e")


def test_returns_not_found_for_unknown_member(conn):
    result = grade_lookup(conn, member="존재하지않는부재", item="x", subitem="", measures={})
    assert result["status"] == "not_found"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_grading.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# backend/app/grading.py
"""부재 하나의 상태평가 등급을 판정한다.

정량 지표가 있으면 코드가 구간 대입으로 등급을 확정한다. 여러 정량 지표가
서로 다른 등급을 가리키면 더 나쁜(알파벳이 더 뒤인) 등급을 채택한다
(1.4절 본문 "정량적, 정성적 평가의 최젓값을 기준으로 산정" 원칙).
정성 지표만 있으면 절대 등급을 확정하지 않고 후보를 그대로 반환한다.
"""
from __future__ import annotations

import operator
import sqlite3

_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}


def grade_lookup(
    conn: sqlite3.Connection,
    member: str,
    item: str,
    subitem: str | None,
    measures: dict[str, float],
    year: int = 2026,
) -> dict:
    cur = conn.execute(
        "SELECT * FROM criteria WHERE year=? AND member=? AND item=? AND subitem=?",
        (year, member, item, subitem or ""),
    )
    rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        return {"status": "not_found"}

    quant_rows = [r for r in rows if r["criterion_type"] == "quant"]
    if quant_rows:
        matched = []
        for r in quant_rows:
            field = r["parsed_field"]
            value = measures.get(field)
            if value is None:
                continue
            ok = True
            if r["parsed_min"] is not None:
                ok = ok and _OPS[r["parsed_min_op"]](value, r["parsed_min"])
            if r["parsed_max"] is not None:
                ok = ok and _OPS[r["parsed_max_op"]](value, r["parsed_max"])
            if ok:
                matched.append({
                    "grade": r["grade"], "criterion_raw": r["criterion_raw"],
                    "table_no": r["table_no"], "page": r["page"],
                })
        if matched:
            worst = max(matched, key=lambda m: m["grade"])
            return {"status": "graded", "grade": worst["grade"], "evidence": matched}
        return {
            "status": "no_match",
            "available_fields": sorted({r["parsed_field"] for r in quant_rows if r["parsed_field"]}),
        }

    qual_rows = [r for r in rows if r["criterion_type"] == "qual"]
    return {
        "status": "needs_judgment",
        "candidates": [
            {"grade": r["grade"], "criterion_raw": r["criterion_raw"], "table_no": r["table_no"], "page": r["page"]}
            for r in qual_rows
        ],
    }
```

- [ ] **Step 4: 테스트 실행해서 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_grading.py -v
git add backend/app/grading.py backend/tests/test_grading.py
git commit -m "feat: grade_lookup 부재 등급 판정 함수 추가"
```

---

### Task 7: `aggregate_structure_grade` — 구조형식별 전체 등급 산정 (①②③단계)

**Files:**
- Create: `backend/app/aggregate.py`
- Test: `backend/tests/test_aggregate.py`

**Interfaces:**
- Consumes: `weight_tables`, `defect_score` 테이블 (Task 5)
- Produces: `aggregate_structure_grade(conn, year: int, structure_type: str, member_grades: dict[str, str], critical_defect_member: str | None = None) -> dict`
  - 반환: `{"grade": "A", "converted_score": 0.1, "contributions": [...], "reason": (optional)}`
  - `MEMBER_TO_DEFECT_ITEM: dict[str, str]` — 부재명(예: "콘크리트 바닥판") → 표1.31의 결함도 평가항목(예: "바닥판")

- [ ] **Step 1: 실패하는 테스트 작성 — 표1.31 실측값으로 계산 검증**

```python
# backend/tests/test_aggregate.py
import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.aggregate import aggregate_structure_grade

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"

STRUCTURE_TYPE = "거더교량 > 일반 거더교 > 일반"
ALL_MEMBERS = {
    "콘크리트 바닥판": "a", "철근콘크리트 거더": "a", "콘크리트 가로보": "a",
    "교대": "a", "기초": "a", "교량받침": "a", "신축이음": "a",
    "아스팔트 콘크리트 교면포장": "a", "배수시설": "a", "난간 및 연석": "a",
}


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_all_grade_a_yields_structure_grade_a(conn):
    # 표1.31 일반거더교(일반) 가중치 합계가 117이므로, 전 부재 a등급(지수 0.10)이면
    # 환산 결함도 점수 = 0.10, 표1.33 A범위(0<=X<0.13) 안에 든다.
    result = aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, ALL_MEMBERS)
    assert result["converted_score"] == pytest.approx(0.10, abs=1e-6)
    assert result["grade"] == "A"


def test_one_bad_member_drags_score_into_c_range(conn):
    # 기초(가중치 21) 하나만 e등급(지수 1.00), 나머지는 a(지수 0.10):
    # (96*0.10 + 21*1.00) / 117 = 0.26154... -> 표1.33 C범위(0.26<=X<0.49)
    grades = dict(ALL_MEMBERS)
    grades["기초"] = "e"
    result = aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, grades)
    assert result["converted_score"] == pytest.approx(30.6 / 117, abs=1e-6)
    assert result["grade"] == "C"


def test_critical_defect_overrides_weighted_average(conn):
    grades = dict(ALL_MEMBERS)
    grades["기초"] = "e"
    result = aggregate_structure_grade(
        conn, 2026, STRUCTURE_TYPE, grades, critical_defect_member="기초",
    )
    assert result["grade"] == "e"  # 가중평균(C)보다 중대결함 부재의 e가 더 나쁘므로 그대로 채택
    assert "중대한 결함" in result["reason"]


def test_unknown_member_name_raises_clear_error(conn):
    with pytest.raises(ValueError, match="알 수 없는 부재명"):
        aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, {"없는부재": "a"})
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_aggregate.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# backend/app/aggregate.py
"""부재별 등급 -> 구조형식별/본교별/전체 시설물 등급 산정 (1.4절 본문 5단계 절차).

① 부재별 상태평가 -> ② 가중치 적용 환산 결함도 점수(표1.31/32) ->
③ 결함도 점수 범위(표1.33)로 구조형식별 등급 -> ④ 연장비 가중합으로 본교 등급 ->
⑤ 본교/램프교/접속교 연장비 가중합으로 전체 등급.
중대한 결함이 발생한 경우, 해당 부재/구조형식의 등급이 가중평균보다 나쁘면 그 등급을 그대로 채택한다.
"""
from __future__ import annotations

import sqlite3

# 표1.10/1.31 부재명 -> 표1.31 '결함도 평가항목' 매핑.
# 새 부재가 추가되면(예: 케이블부재, 강 거더 등 특수교/강교 부재) 이 표를 함께 갱신해야 한다.
MEMBER_TO_DEFECT_ITEM: dict[str, str] = {
    "콘크리트 바닥판": "바닥판", "강 바닥판": "바닥판", "프리스트레스 콘크리트 바닥판": "바닥판",
    "철근콘크리트 거더": "주 형", "프리스트레스 콘크리트 거더": "주 형",
    "콘크리트 가로보": "2차부재", "강 가로보와 세로보": "2차부재",
    "교대": "교대/교각", "콘크리트 교각": "교대/교각", "강 교각(강 주탑)": "교대/교각",
    "기초": "기초",
    "교량받침": "교량받침",
    "신축이음": "신축이음",
    "아스팔트 콘크리트 교면포장": "교면포장", "시멘트 콘크리트 교면포장": "교면포장",
    "배수시설": "배수시설",
    "난간 및 연석": "난간/연석",
}

_GRADE_TO_LETTER_KEY = str.upper


def _defect_index_for_grade(conn: sqlite3.Connection, year: int, grade: str) -> float | None:
    row = conn.execute(
        "SELECT index_value FROM defect_score WHERE year=? AND grade=?",
        (year, _GRADE_TO_LETTER_KEY(grade)),
    ).fetchone()
    return row["index_value"] if row else None


def _grade_for_score(conn: sqlite3.Connection, year: int, score: float) -> str | None:
    row = conn.execute(
        "SELECT grade FROM defect_score WHERE year=? "
        "AND (range_min IS NULL OR ? >= range_min) "
        "AND (range_max IS NULL OR ? < range_max)",
        (year, score, score),
    ).fetchone()
    return row["grade"] if row else None


def aggregate_structure_grade(
    conn: sqlite3.Connection,
    year: int,
    structure_type: str,
    member_grades: dict[str, str],
    critical_defect_member: str | None = None,
) -> dict:
    total_weight = 0.0
    weighted_index_sum = 0.0
    contributions = []

    for member, grade in member_grades.items():
        defect_item = MEMBER_TO_DEFECT_ITEM.get(member)
        if defect_item is None:
            raise ValueError(f"알 수 없는 부재명입니다: {member!r} (MEMBER_TO_DEFECT_ITEM에 등록되지 않음)")
        weight_row = conn.execute(
            "SELECT weight FROM weight_tables WHERE year=? AND defect_item=? AND structure_type=?",
            (year, defect_item, structure_type),
        ).fetchone()
        if weight_row is None or weight_row["weight"] is None:
            continue
        idx = _defect_index_for_grade(conn, year, grade)
        weighted_index_sum += weight_row["weight"] * idx
        total_weight += weight_row["weight"]
        contributions.append({"member": member, "grade": grade, "weight": weight_row["weight"]})

    converted_score = weighted_index_sum / total_weight if total_weight else None
    computed_grade = _grade_for_score(conn, year, converted_score) if converted_score is not None else None
    result = {"grade": computed_grade, "converted_score": converted_score, "contributions": contributions}

    if critical_defect_member:
        critical_grade = member_grades[critical_defect_member]
        critical_index = _defect_index_for_grade(conn, year, critical_grade)
        if critical_index is not None and (converted_score is None or critical_index > converted_score):
            result["grade"] = critical_grade
            result["reason"] = f"중대한 결함 부재({critical_defect_member})의 등급을 우선 적용"

    return result
```

- [ ] **Step 4: 테스트 실행해서 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_aggregate.py -v
git add backend/app/aggregate.py backend/tests/test_aggregate.py
git commit -m "feat: aggregate_structure_grade 구조형식별 등급 산정 추가"
```

---

### Task 8: `aggregate_bridge_grade` — 본교/전체 시설물 등급 (④⑤단계)

**Files:**
- Modify: `backend/app/aggregate.py`
- Modify: `backend/tests/test_aggregate.py`

**Interfaces:**
- Consumes: Task 7의 `_grade_for_score` (같은 파일 내 재사용), `aggregate_structure_grade`의 반환값 형태(`{"grade", "converted_score"}`)
- Produces: `aggregate_bridge_grade(conn, year: int, structure_results: dict[str, dict], span_ratios: dict[str, float], critical_defect_structure: str | None = None) -> dict`
  - `structure_results`의 각 값은 `aggregate_structure_grade`의 반환 dict (`converted_score`, `grade` 키 사용)
  - 반환: `{"grade": "B", "converted_score": 0.18, "reason": (optional)}`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/test_aggregate.py 에 추가
from app.aggregate import aggregate_bridge_grade


def test_aggregate_bridge_grade_weights_by_span_ratio(conn):
    structure_results = {
        "강거더교_구간": {"grade": "A", "converted_score": 0.10},
        "PSC거더교_구간": {"grade": "C", "converted_score": 0.30},
    }
    span_ratios = {"강거더교_구간": 300.0, "PSC거더교_구간": 100.0}  # 연장(m) 비율
    result = aggregate_bridge_grade(conn, 2026, structure_results, span_ratios)

    expected_score = (0.10 * 300 + 0.30 * 100) / 400  # = 0.15
    assert result["converted_score"] == pytest.approx(expected_score, abs=1e-6)
    assert result["grade"] == "B"  # 표1.33: 0.13<=X<0.26


def test_critical_defect_structure_overrides_bridge_average(conn):
    structure_results = {
        "강거더교_구간": {"grade": "A", "converted_score": 0.10},
        "PSC거더교_구간": {"grade": "E", "converted_score": 1.00},
    }
    span_ratios = {"강거더교_구간": 300.0, "PSC거더교_구간": 100.0}
    result = aggregate_bridge_grade(
        conn, 2026, structure_results, span_ratios, critical_defect_structure="PSC거더교_구간",
    )
    assert result["grade"] == "E"
    assert "중대한 결함" in result["reason"]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_aggregate.py::test_aggregate_bridge_grade_weights_by_span_ratio -v
```
Expected: FAIL (`ImportError: cannot import name 'aggregate_bridge_grade'`)

- [ ] **Step 3: 구현 (`backend/app/aggregate.py` 파일 끝에 추가)**

```python
def aggregate_bridge_grade(
    conn: sqlite3.Connection,
    year: int,
    structure_results: dict[str, dict],
    span_ratios: dict[str, float],
    critical_defect_structure: str | None = None,
) -> dict:
    """본교(또는 램프교/접속교/전체 시설물)의 등급을 연장비 가중합으로 산정한다.
    같은 함수로 ④단계(구조형식들 -> 본교)와 ⑤단계(본교/램프교/접속교 -> 전체)를 모두 처리한다."""
    total_ratio = sum(span_ratios.values())
    weighted_sum = sum(
        structure_results[name]["converted_score"] * ratio
        for name, ratio in span_ratios.items()
        if structure_results[name]["converted_score"] is not None
    )
    converted_score = weighted_sum / total_ratio if total_ratio else None
    computed_grade = _grade_for_score(conn, year, converted_score) if converted_score is not None else None
    result = {"grade": computed_grade, "converted_score": converted_score}

    if critical_defect_structure:
        critical = structure_results[critical_defect_structure]
        if critical["converted_score"] is not None and (
            converted_score is None or critical["converted_score"] > converted_score
        ):
            result["grade"] = critical["grade"]
            result["converted_score"] = critical["converted_score"]
            result["reason"] = f"중대한 결함 구조형식({critical_defect_structure})의 등급을 우선 적용"

    return result
```

- [ ] **Step 4: 테스트 실행해서 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_aggregate.py -v
git add backend/app/aggregate.py backend/tests/test_aggregate.py
git commit -m "feat: aggregate_bridge_grade 본교/전체 시설물 등급 산정 추가"
```

---

### Task 9: `compare_years` — 연도별 기준 비교

**Files:**
- Create: `backend/app/compare.py`
- Test: `backend/tests/test_compare.py`

**Interfaces:**
- Consumes: `criteria` 테이블 (Task 5)
- Produces: `compare_years(conn, member: str, item: str, subitem: str | None, years: list[int]) -> dict`
  - 반환: `{"by_year": {2024: [...], 2026: [...]}, "changed_grades": {"c": {2024: [...], 2026: [...]}}}`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/test_compare.py
import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.compare import compare_years

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_detects_member_newly_introduced_in_2026(conn):
    # 월류(여유고 조사)는 2026 신설 부재 -> 실제 데이터로 검증된 사실
    result = compare_years(conn, member="월류(여유고 조사)", item="여유고 검토1)", subitem="", years=[2024, 2026])
    assert result["by_year"][2024] == []
    assert len(result["by_year"][2026]) > 0


def test_unchanged_criterion_reports_no_diff(conn):
    # 표1.11 콘크리트 바닥판은 2022~2026 원문이 동일함을 diff로 이미 확인함
    result = compare_years(
        conn, member="콘크리트 바닥판", item="균열1)", subitem="1방향 균열", years=[2022, 2026],
    )
    assert result["changed_grades"] == {}


def test_changed_criterion_text_is_reported(conn):
    conn.execute(
        "INSERT INTO criteria (year, section, table_no, table_title, member, item, subitem, grade, "
        "criterion_raw, criterion_type, page, source_path) VALUES "
        "(2024, '1.4', 't', 'title', '테스트부재', '테스트항목', '', 'b', '균열폭 0.1이상', 'quant', 1, 'x')"
    )
    conn.execute(
        "INSERT INTO criteria (year, section, table_no, table_title, member, item, subitem, grade, "
        "criterion_raw, criterion_type, page, source_path) VALUES "
        "(2026, '1.4', 't', 'title', '테스트부재', '테스트항목', '', 'b', '균열폭 0.2이상', 'quant', 1, 'x')"
    )
    conn.commit()
    result = compare_years(conn, member="테스트부재", item="테스트항목", subitem="", years=[2024, 2026])
    assert "b" in result["changed_grades"]
    assert result["changed_grades"]["b"][2024] == ["균열폭 0.1이상"]
    assert result["changed_grades"]["b"][2026] == ["균열폭 0.2이상"]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_compare.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# backend/app/compare.py
"""(부재, 평가항목, 세부항목) 키로 연도별 기준을 비교한다.
표 번호는 연도마다 밀리므로(예: 표1.34->1.35~37) 표 번호가 아니라 이 키로 매칭한다."""
from __future__ import annotations

import sqlite3


def compare_years(
    conn: sqlite3.Connection,
    member: str,
    item: str,
    subitem: str | None,
    years: list[int],
) -> dict:
    by_year: dict[int, list[dict]] = {}
    for year in years:
        cur = conn.execute(
            "SELECT grade, criterion_raw, table_no, page FROM criteria "
            "WHERE year=? AND member=? AND item=? AND subitem=? ORDER BY grade, criterion_raw",
            (year, member, item, subitem or ""),
        )
        by_year[year] = [dict(r) for r in cur.fetchall()]

    all_grades = sorted({row["grade"] for rows in by_year.values() for row in rows})
    changed_grades: dict[str, dict[int, list[str]]] = {}
    for grade in all_grades:
        texts_by_year = {
            year: sorted(r["criterion_raw"] for r in rows if r["grade"] == grade)
            for year, rows in by_year.items()
        }
        distinct = {tuple(v) for v in texts_by_year.values()}
        if len(distinct) > 1:
            changed_grades[grade] = texts_by_year

    return {"by_year": by_year, "changed_grades": changed_grades}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_compare.py -v
git add backend/app/compare.py backend/tests/test_compare.py
git commit -m "feat: compare_years 연도별 기준 비교 함수 추가"
```

---

### Task 10: `search_text` — 서술형 본문 검색 (TF-IDF)

**Files:**
- Create: `backend/app/search.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: `text_docs` 테이블 (Task 5)
- Produces: `class TextSearcher: __init__(self, conn, year: int = 2026)`, `.search(query: str, section: str | None = None, top_k: int = 5) -> list[dict]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/test_search.py
import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.search import TextSearcher

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_finds_relevant_paragraph_for_definition_query(conn):
    searcher = TextSearcher(conn, year=2026)
    results = searcher.search("특수교는 어떤 교량인가")
    assert len(results) > 0
    assert any("특수교" in r["paragraph"] for r in results)


def test_section_filter_narrows_results(conn):
    searcher = TextSearcher(conn, year=2026)
    results = searcher.search("보수 보강", section="1.7 보수·보강 방법")
    assert len(results) > 0
    assert all(r["section"] == "1.7 보수·보강 방법" for r in results)


def test_irrelevant_query_returns_empty_or_low_score(conn):
    searcher = TextSearcher(conn, year=2026)
    results = searcher.search("xyz불가능한검색어123")
    assert results == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_search.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# backend/app/search.py
"""text_docs(서술형 본문)에 대한 TF-IDF 코사인 유사도 검색.
표(criteria/weight_tables/defect_score)는 DB 질의로 정확히 계산하고,
이 모듈은 1.1~1.7절 서술형 본문에 대한 자유검색만 담당한다."""
from __future__ import annotations

import sqlite3

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TextSearcher:
    def __init__(self, conn: sqlite3.Connection, year: int = 2026):
        self.year = year
        cur = conn.execute(
            "SELECT id, section, heading_path, paragraph, source_path FROM text_docs WHERE year=?",
            (year,),
        )
        self.rows = [dict(r) for r in cur.fetchall()]
        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform([r["paragraph"] for r in self.rows]) if self.rows else None

    def search(self, query: str, section: str | None = None, top_k: int = 5) -> list[dict]:
        if not self.rows:
            return []
        candidates = self.rows
        matrix = self.matrix
        if section:
            idx = [i for i, r in enumerate(self.rows) if r["section"] == section]
            if not idx:
                return []
            candidates = [self.rows[i] for i in idx]
            matrix = self.matrix[idx]

        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, matrix)[0]
        ranked = sims.argsort()[::-1][:top_k]
        return [{**candidates[i], "score": float(sims[i])} for i in ranked if sims[i] > 0]
```

- [ ] **Step 4: 테스트 실행해서 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_search.py -v
git add backend/app/search.py backend/tests/test_search.py
git commit -m "feat: TF-IDF 기반 서술형 본문 검색 추가"
```

---

### Task 11: FastAPI 엔드포인트

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: Task 6~10의 모든 함수/클래스
- Produces: HTTP 엔드포인트
  - `POST /inspection/grade`
  - `POST /inspection/aggregate-structure`
  - `POST /inspection/aggregate-bridge`
  - `GET /inspection/schema?year=` — `(member,item,subitem)` 전체 목록 (프론트 드롭다운용)
  - `GET /inspection/fields?member=&item=&subitem=&year=` — 해당 항목의 정량 필드명(균열폭 등) 목록 (프론트 입력폼 동적 생성용)
  - `GET /compare?member=&item=&subitem=&years=2022,2024,2026`
  - `GET /search?q=&section=&year=`

- [ ] **Step 1: `requirements.txt`에 의존성 추가**

```
# backend/requirements.txt
fastapi
uvicorn[standard]
scikit-learn
pytest
httpx
langchain
langchain-anthropic
```

```bash
cd backend && pip install -r requirements.txt
```

- [ ] **Step 2: 실패하는 테스트 작성 (build_db로 만든 실제 DB를 앱에 주입)**

```python
# backend/tests/test_api.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.build_db import main as build_main
import app.main as main_module

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    main_module.DB_PATH = str(db_path)
    main_module._searcher_cache.clear()
    return TestClient(main_module.app)


def test_grade_endpoint_returns_graded_result(client):
    resp = client.post("/inspection/grade", json={
        "member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열",
        "measures": {"균열폭": 0.35}, "year": 2026,
    })
    assert resp.status_code == 200
    assert resp.json()["grade"] == "c"


def test_schema_endpoint_lists_known_member(client):
    resp = client.get("/inspection/schema", params={"year": 2026})
    assert resp.status_code == 200
    members = {row["member"] for row in resp.json()}
    assert "콘크리트 바닥판" in members


def test_fields_endpoint_lists_quant_fields(client):
    resp = client.get("/inspection/fields", params={
        "member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열", "year": 2026,
    })
    assert resp.status_code == 200
    fields = {row["parsed_field"] for row in resp.json()}
    assert "균열폭" in fields
    assert "균열률" in fields


def test_compare_endpoint(client):
    resp = client.get("/compare", params={
        "member": "월류(여유고 조사)", "item": "여유고 검토1)", "years": "2024,2026",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_year"]["2024"] == []


def test_search_endpoint(client):
    resp = client.get("/search", params={"q": "특수교는 어떤 교량인가", "year": 2026})
    assert resp.status_code == 200
    assert len(resp.json()) > 0
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_api.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: 구현**

```python
# backend/app/main.py
"""FastAPI 앱: grade/aggregate/compare/search 엔드포인트."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from app.grading import grade_lookup
from app.aggregate import aggregate_structure_grade, aggregate_bridge_grade
from app.compare import compare_years
from app.search import TextSearcher

DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "bridge_qna.db")
_searcher_cache: dict[int, TextSearcher] = {}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_searcher(year: int) -> TextSearcher:
    if year not in _searcher_cache:
        _searcher_cache[year] = TextSearcher(get_conn(), year=year)
    return _searcher_cache[year]


app = FastAPI(title="교량편 QnA API")


class GradeRequest(BaseModel):
    member: str
    item: str
    subitem: str | None = None
    measures: dict[str, float]
    year: int = 2026


@app.post("/inspection/grade")
def api_grade(req: GradeRequest):
    return grade_lookup(get_conn(), req.member, req.item, req.subitem, req.measures, req.year)


class AggregateStructureRequest(BaseModel):
    year: int = 2026
    structure_type: str
    member_grades: dict[str, str]
    critical_defect_member: str | None = None


@app.post("/inspection/aggregate-structure")
def api_aggregate_structure(req: AggregateStructureRequest):
    return aggregate_structure_grade(
        get_conn(), req.year, req.structure_type, req.member_grades, req.critical_defect_member,
    )


class AggregateBridgeRequest(BaseModel):
    year: int = 2026
    structure_results: dict[str, dict]
    span_ratios: dict[str, float]
    critical_defect_structure: str | None = None


@app.post("/inspection/aggregate-bridge")
def api_aggregate_bridge(req: AggregateBridgeRequest):
    return aggregate_bridge_grade(
        get_conn(), req.year, req.structure_results, req.span_ratios, req.critical_defect_structure,
    )


@app.get("/inspection/schema")
def api_schema(year: int = 2026):
    conn = get_conn()
    cur = conn.execute(
        "SELECT DISTINCT member, item, subitem FROM criteria WHERE year=? ORDER BY member, item, subitem",
        (year,),
    )
    return [dict(r) for r in cur.fetchall()]


@app.get("/inspection/fields")
def api_fields(member: str, item: str, subitem: str = "", year: int = 2026):
    conn = get_conn()
    cur = conn.execute(
        "SELECT DISTINCT parsed_field, parsed_unit FROM criteria "
        "WHERE year=? AND member=? AND item=? AND subitem=? AND criterion_type='quant'",
        (year, member, item, subitem),
    )
    return [dict(r) for r in cur.fetchall()]


@app.get("/compare")
def api_compare(member: str, item: str, subitem: str = "", years: str = "2022,2023,2024,2026"):
    conn = get_conn()
    year_list = [int(y) for y in years.split(",")]
    result = compare_years(conn, member, item, subitem, year_list)
    return {
        "by_year": {str(y): rows for y, rows in result["by_year"].items()},
        "changed_grades": {
            grade: {str(y): texts for y, texts in by_year.items()}
            for grade, by_year in result["changed_grades"].items()
        },
    }


@app.get("/search")
def api_search(q: str, section: str | None = None, year: int = 2026):
    return get_searcher(year).search(q, section)
```

- [ ] **Step 5: 테스트 실행해서 통과 확인, 커밋**

```bash
cd backend && python -m pytest tests/test_api.py -v
git add backend/app/main.py backend/tests/test_api.py backend/requirements.txt
git commit -m "feat: FastAPI grade/aggregate/compare/search 엔드포인트 추가"
```

---

### Task 12: LLM 도구호출 `/chat` 엔드포인트

**Files:**
- Create: `backend/app/llm_config.py`
- Create: `backend/app/llm_tools.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_llm_tools.py`

**Interfaces:**
- Consumes: `grade_lookup`(Task 6), `compare_years`(Task 9), `TextSearcher`(Task 10), `get_conn`/`get_searcher`(Task 11, `main.py`에서 import)
- Produces:
  - `load_config() -> dict` (`QA/qna.py`의 provider 자동판별 로직 이식)
  - `build_llm(config: dict)`
  - `run_chat(llm, message: str) -> str`
  - `POST /chat` 엔드포인트, 요청 `{"message": str}` -> 응답 `{"answer": str}`

- [ ] **Step 1: `llm_config.py` — 기존 `QA/qna.py` 로직 이식**

```python
# backend/app/llm_config.py
"""api_key.txt에서 provider/model/key를 읽는다. QA/qna.py의 로직을 그대로 이식했다."""
from __future__ import annotations

from pathlib import Path

API_KEY_FILE = Path(__file__).resolve().parent.parent / "api_key.txt"

KEY_PREFIX_MAP = [("sk-ant-", "anthropic"), ("nvapi-", "nvidia"), ("sk-", "openai")]
DEFAULT_MODEL_BY_PROVIDER = {
    "anthropic": "claude-opus-5",
    "nvidia": "nvidia/nemotron-3-nano-30b-a3b",
    "openai": "gpt-4o",
}


def detect_provider(key: str) -> str:
    for prefix, provider in KEY_PREFIX_MAP:
        if key.startswith(prefix):
            return provider
    raise ValueError(f"API 키 형식으로 provider를 자동 판별하지 못했습니다: '{key[:8]}...'")


def load_config() -> dict:
    if not API_KEY_FILE.exists():
        raise FileNotFoundError(f"{API_KEY_FILE} 파일이 없습니다.")

    config: dict = {"key": None, "provider": None, "model": None}
    for raw_line in API_KEY_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and line.split("=", 1)[0].strip().lower() in ("provider", "model", "key"):
            field, value = line.split("=", 1)
            config[field.strip().lower()] = value.strip()
        elif config["key"] is None:
            config["key"] = line

    if not config["key"] or "여기에" in config["key"]:
        raise ValueError(f"{API_KEY_FILE} 파일에 실제 API 키를 입력해야 합니다.")
    if not config["provider"]:
        config["provider"] = detect_provider(config["key"])
    if not config["model"]:
        config["model"] = DEFAULT_MODEL_BY_PROVIDER.get(config["provider"])
    return config


def build_llm(config: dict):
    provider = config["provider"]
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config["model"], api_key=config["key"], max_tokens=2048)
    elif provider == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(model=config["model"], api_key=config["key"], timeout=120)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=config["model"], api_key=config["key"])
    raise ValueError(f"지원하지 않는 provider입니다: {provider}")
```

- [ ] **Step 2: 실패하는 테스트 작성 (도구 실행 루프만 검증, 실제 API 호출은 가짜 LLM으로 대체)**

```python
# backend/tests/test_llm_tools.py
from langchain_core.messages import AIMessage

from app.llm_tools import run_chat, TOOLS_BY_NAME


class _FakeLLMWithTools:
    """실제 API를 호출하지 않고 도구 실행 루프(run_chat)만 검증하기 위한 가짜 LLM."""

    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


class _FakeBoundLLM:
    def __init__(self, responses):
        self._llm = _FakeLLMWithTools(responses)

    def invoke(self, messages):
        return self._llm.invoke(messages)


class _FakeLLM:
    def __init__(self, responses):
        self._responses = responses

    def bind_tools(self, tools):
        return _FakeBoundLLM(self._responses)


def test_run_chat_executes_tool_call_then_returns_final_answer(monkeypatch):
    tool_call_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "grade_lookup_tool",
            "args": {"member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열",
                      "measures": {"균열폭": 0.35}, "year": 2026},
            "id": "call_1",
        }],
    )
    final_response = AIMessage(content="c등급입니다.", tool_calls=[])

    called_with = {}
    def fake_tool_invoke(args):
        called_with.update(args)
        return {"status": "graded", "grade": "c", "evidence": []}

    monkeypatch.setitem(TOOLS_BY_NAME, "grade_lookup_tool", type(
        "T", (), {"invoke": staticmethod(fake_tool_invoke)},
    )())

    llm = _FakeLLM([tool_call_response, final_response])
    answer = run_chat(llm, "바닥판에 0.35mm 균열이면 몇 등급인가요?")

    assert answer == "c등급입니다."
    assert called_with["member"] == "콘크리트 바닥판"
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
cd backend && python -m pytest tests/test_llm_tools.py -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: `llm_tools.py` 구현**

```python
# backend/app/llm_tools.py
"""LLM 도구호출 오케스트레이션. 등급 판정/구간 비교는 도구(파이썬 함수)가 계산하고
LLM은 도구 결과를 인용해 자연어로 설명만 한다."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from app.grading import grade_lookup
from app.compare import compare_years


def _get_conn():
    from app.main import get_conn
    return get_conn()


def _get_searcher(year: int):
    from app.main import get_searcher
    return get_searcher(year)


@tool
def grade_lookup_tool(member: str, item: str, subitem: str, measures: dict, year: int = 2026) -> dict:
    """부재/평가항목/세부항목과 측정값(예: 균열폭, 균열률)으로 상태평가 등급을 판정한다."""
    return grade_lookup(_get_conn(), member, item, subitem, measures, year)


@tool
def compare_years_tool(member: str, item: str, subitem: str, years: list[int]) -> dict:
    """같은 부재/평가항목/세부항목의 판정기준이 연도별로 어떻게 다른지 비교한다."""
    return compare_years(_get_conn(), member, item, subitem, years)


@tool
def search_text_tool(query: str, section: str = "", year: int = 2026) -> list:
    """지침서 서술형 본문(정의, 절차, 설명)을 검색한다. 표 기반 등급판정은 grade_lookup_tool을 쓴다."""
    return _get_searcher(year).search(query, section or None)


TOOLS = [grade_lookup_tool, compare_years_tool, search_text_tool]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYSTEM_PROMPT = (
    "당신은 「시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편」에 정통한 전문가입니다. "
    "등급 판정이나 구간 비교가 필요하면 반드시 도구를 호출하고, 직접 숫자를 비교해 등급을 판단하지 마세요. "
    "도구가 'needs_judgment'를 반환하면 이는 정성적 판단이 필요하다는 뜻이므로 최종 등급을 단정하지 말고 "
    "후보와 근거를 제시한 뒤 점검자의 판단이 필요하다고 안내하세요. 항상 표 번호와 면수를 출처로 인용하세요."
)


def run_chat(llm, message: str) -> str:
    llm_with_tools = llm.bind_tools(TOOLS)
    messages = [HumanMessage(content=f"{SYSTEM_PROMPT}\n\n질문: {message}")]
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    while response.tool_calls:
        for call in response.tool_calls:
            result = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        response = llm_with_tools.invoke(messages)
        messages.append(response)

    return response.content
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

```bash
cd backend && python -m pytest tests/test_llm_tools.py -v
```
Expected: PASS

- [ ] **Step 6: `/chat` 엔드포인트를 `main.py`에 추가**

```python
# backend/app/main.py 끝에 추가
from app.llm_config import load_config, build_llm
from app.llm_tools import run_chat


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def api_chat(req: ChatRequest):
    llm = build_llm(load_config())
    answer = run_chat(llm, req.message)
    return {"answer": answer}
```

- [ ] **Step 7: `api_key.txt` 준비 확인 (실제 호출 전 수동 확인용, 자동테스트 아님)**

```bash
cat backend/api_key.txt 2>/dev/null || echo "backend/api_key.txt가 없습니다 - QA/api_key.txt를 참고해 만드세요"
```
없으면 `QA/api_key.txt`를 `backend/api_key.txt`로 복사하고 실제 키가 들어있는지 확인한다.

- [ ] **Step 8: 커밋**

```bash
git add backend/app/llm_config.py backend/app/llm_tools.py backend/app/main.py backend/tests/test_llm_tools.py
git commit -m "feat: LLM 도구호출 /chat 엔드포인트 추가"
```

---

### Task 13: React 프론트엔드 — 채팅 탭

**Files:**
- Create: `frontend/` (Vite 스캐폴딩)
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `POST /chat` (Task 12)
- Produces: `sendChat(message: string): Promise<string>`, `<ChatPanel />` 컴포넌트

- [ ] **Step 1: Vite 스캐폴딩**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```

- [ ] **Step 2: `api.ts` 작성**

```typescript
// frontend/src/api.ts
const API_BASE = "http://localhost:8000";

export async function sendChat(message: string): Promise<string> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`chat 요청 실패: ${res.status}`);
  const data = await res.json();
  return data.answer as string;
}

export interface GradeRequest {
  member: string;
  item: string;
  subitem?: string;
  measures: Record<string, number>;
  year?: number;
}

export async function gradeLookup(payload: GradeRequest) {
  const res = await fetch(`${API_BASE}/inspection/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export interface SchemaRow {
  member: string;
  item: string;
  subitem: string;
}

export async function fetchSchema(year = 2026): Promise<SchemaRow[]> {
  const res = await fetch(`${API_BASE}/inspection/schema?year=${year}`);
  return res.json();
}

export interface FieldRow {
  parsed_field: string;
  parsed_unit: string | null;
}

export async function fetchFields(
  member: string, item: string, subitem: string, year = 2026,
): Promise<FieldRow[]> {
  const params = new URLSearchParams({ member, item, subitem, year: String(year) });
  const res = await fetch(`${API_BASE}/inspection/fields?${params}`);
  return res.json();
}

export interface AggregateStructureRequest {
  year?: number;
  structure_type: string;
  member_grades: Record<string, string>;
  critical_defect_member?: string;
}

export async function aggregateStructure(payload: AggregateStructureRequest) {
  const res = await fetch(`${API_BASE}/inspection/aggregate-structure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
```

- [ ] **Step 3: `ChatPanel.tsx` 작성**

```tsx
// frontend/src/components/ChatPanel.tsx
import { useState } from "react";
import { sendChat } from "../api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    const question = input.trim();
    if (!question || loading) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const answer = await sendChat(question);
      setMessages((prev) => [...prev, { role: "assistant", text: answer }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", text: `오류: ${(err as Error).message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-message chat-message--${m.role}`}>
            {m.text}
          </div>
        ))}
        {loading && <div className="chat-message chat-message--assistant">답변 생성 중...</div>}
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
          placeholder="질문을 입력하세요"
        />
        <button onClick={handleSend} disabled={loading}>전송</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `App.tsx`에서 `ChatPanel` 렌더링**

```tsx
// frontend/src/App.tsx
import { ChatPanel } from "./components/ChatPanel";
import "./App.css";

function App() {
  return (
    <div className="app">
      <h1>정밀안전점검·진단 교량편 QnA</h1>
      <ChatPanel />
    </div>
  );
}

export default App;
```

- [ ] **Step 5: 개발 서버로 수동 확인**

터미널 1 (백엔드):
```bash
cd backend && uvicorn app.main:app --reload --port 8000
```
터미널 2 (프론트):
```bash
cd frontend && npm run dev
```
브라우저에서 `http://localhost:5173` 접속 → "콘크리트 바닥판에 균열폭 0.35mm면 몇 등급인가요?" 입력 → 답변에 등급과 근거(표 번호)가 포함되는지 확인.

- [ ] **Step 6: 커밋**

```bash
git add frontend/
git commit -m "feat: React 채팅 탭 (ChatPanel) 추가"
```

---

### Task 14: React 프론트엔드 — 점검표 탭 (`InspectionSheet`)

**Files:**
- Create: `frontend/src/components/InspectionSheet.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchSchema`, `fetchFields`, `gradeLookup`, `aggregateStructure` (Task 13의 `api.ts`)
- Produces: `<InspectionSheet />` — 부재 선택 → 손상 수치 입력 → 개별 등급 표시 → "전체 등급 계산" 결과 표시

- [ ] **Step 1: `InspectionSheet.tsx` 작성**

```tsx
// frontend/src/components/InspectionSheet.tsx
import { useEffect, useState } from "react";
import {
  fetchSchema, fetchFields, gradeLookup, aggregateStructure,
  type SchemaRow, type FieldRow,
} from "../api";

interface RowState {
  member: string;
  item: string;
  subitem: string;
  measures: Record<string, string>;
  fields: FieldRow[];
  result: any;
}

export function InspectionSheet() {
  const [schema, setSchema] = useState<SchemaRow[]>([]);
  const [rows, setRows] = useState<RowState[]>([]);
  const [structureType, setStructureType] = useState("거더교량 > 일반 거더교 > 일반");
  const [aggregateResult, setAggregateResult] = useState<any>(null);

  useEffect(() => {
    fetchSchema(2026).then(setSchema);
  }, []);

  const members = Array.from(new Set(schema.map((s) => s.member)));

  function addRow(member: string) {
    const first = schema.find((s) => s.member === member);
    if (!first) return;
    const newRow: RowState = {
      member, item: first.item, subitem: first.subitem,
      measures: {}, fields: [], result: null,
    };
    setRows((prev) => [...prev, newRow]);
    fetchFields(member, first.item, first.subitem).then((fields) => {
      setRows((prev) =>
        prev.map((r) => (r === newRow ? { ...r, fields } : r)),
      );
    });
  }

  async function runGrade(index: number) {
    const row = rows[index];
    const measures: Record<string, number> = {};
    for (const [k, v] of Object.entries(row.measures)) {
      const num = parseFloat(v);
      if (!Number.isNaN(num)) measures[k] = num;
    }
    const result = await gradeLookup({ member: row.member, item: row.item, subitem: row.subitem, measures });
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, result } : r)));
  }

  async function runAggregate() {
    const memberGrades: Record<string, string> = {};
    for (const row of rows) {
      if (row.result?.grade) memberGrades[row.member] = row.result.grade;
    }
    const result = await aggregateStructure({ structure_type: structureType, member_grades: memberGrades });
    setAggregateResult(result);
  }

  return (
    <div className="inspection-sheet">
      <div className="member-picker">
        <select onChange={(e) => e.target.value && addRow(e.target.value)} value="">
          <option value="">+ 부재 추가</option>
          {members.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {rows.map((row, i) => (
        <div key={i} className="inspection-row">
          <strong>{row.member}</strong> / {row.item} / {row.subitem}
          {row.fields.map((f) => (
            <input
              key={f.parsed_field}
              placeholder={`${f.parsed_field}${f.parsed_unit ? ` (${f.parsed_unit})` : ""}`}
              onChange={(e) =>
                setRows((prev) =>
                  prev.map((r, idx) =>
                    idx === i ? { ...r, measures: { ...r.measures, [f.parsed_field]: e.target.value } } : r,
                  ),
                )
              }
            />
          ))}
          <button onClick={() => runGrade(i)}>등급 판정</button>
          {row.result && (
            <span className="result">
              {row.result.status === "graded" && `등급: ${row.result.grade}`}
              {row.result.status === "needs_judgment" && "정성 판단 필요 (후보 확인)"}
              {row.result.status === "no_match" && "구간 불일치"}
            </span>
          )}
        </div>
      ))}

      <div className="structure-picker">
        <label>구조형식: </label>
        <input value={structureType} onChange={(e) => setStructureType(e.target.value)} />
        <button onClick={runAggregate}>전체 등급 계산</button>
      </div>

      {aggregateResult && (
        <div className="aggregate-result">
          환산 결함도 점수: {aggregateResult.converted_score?.toFixed(4)} → 등급: {aggregateResult.grade}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: `App.tsx`에 탭 전환 추가**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { InspectionSheet } from "./components/InspectionSheet";
import "./App.css";

function App() {
  const [tab, setTab] = useState<"chat" | "inspection">("chat");

  return (
    <div className="app">
      <h1>정밀안전점검·진단 교량편 QnA</h1>
      <div className="tabs">
        <button onClick={() => setTab("chat")} disabled={tab === "chat"}>채팅</button>
        <button onClick={() => setTab("inspection")} disabled={tab === "inspection"}>점검표</button>
      </div>
      {tab === "chat" ? <ChatPanel /> : <InspectionSheet />}
    </div>
  );
}

export default App;
```

- [ ] **Step 3: 개발 서버로 수동 확인**

백엔드/프론트 모두 실행 중인 상태에서 `http://localhost:5173`:
1. "점검표" 탭 클릭 → 부재 드롭다운에서 "콘크리트 바닥판" 선택
2. "균열폭" 입력창에 `0.35` 입력 → "등급 판정" 클릭 → "등급: c" 표시 확인
3. 여러 부재를 추가해 모두 등급을 매긴 뒤 "전체 등급 계산" 클릭 → 환산 결함도 점수와 등급 표시 확인

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/components/InspectionSheet.tsx frontend/src/App.tsx
git commit -m "feat: React 점검표 탭 (InspectionSheet) 추가"
```

---

## 스펙 커버리지 점검

| 스펙 섹션 | 담당 Task |
|---|---|
| 5. 데이터 모델 | Task 1~5 |
| 6.1 정량 파서 | Task 2 |
| 6.2 grade_lookup | Task 6 |
| 6.3 aggregate_grade (5단계) | Task 7, 8 |
| 6.4 compare_years | Task 9 |
| 7. 백엔드 API | Task 11, 12 |
| 8. 프론트엔드 | Task 13, 14 |
| 3. 범위 외(보수보강 매핑, 공통편) | 계획에 포함하지 않음 (의도적) |
