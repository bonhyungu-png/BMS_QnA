# -*- coding: utf-8 -*-
"""1.4 상태평가기준 및 방법 안의 표를 전부(이미 뽑은 21개 포함 전수 스캔) 찾아서,
아직 안 뽑은 것만 새로 KV 파일로 만들고, 본문(text) 파일의 표참조 줄도
빠진 곳을 채운다.

번호가 있는 표([표 1.xx])는 번호+원문 제목으로 이름 짓는다.
번호가 없는 표는 그 표 바로 위에서 가장 가까운 소목차(1)~n)) 제목을,
그것도 없으면 가/나/다/라 제목을 이름으로 쓴다('표_추락방지시설'처럼).

표 내용은 두 가지 형태 중 하나로 만든다.
  · 등급표(첫 칸이 a~e로만 이루어진 표) → 기존 부재별 상태평가기준표와
    똑같은 (등급 × 평가항목) KV 블록.
  · 그 외 일반표(가중치표·분류표·환산표 등, 행이 등급이 아닌 표) → 행 단위
    KV 블록. 각 행을 그대로 키:값으로 남기고 등급이라는 개념을 억지로
    씌우지 않는다.
"""
import re
import collections
import pdfplumber
from 공용 import (라벨정리, 항목쪼개기, 헤더행수, 펼치기, 부재명, 파일명 as 파일명_등급표,
                 원본폴더, 판본)
from 추출_본문 import (문서형식감지, 분류, 캡션패턴, 가나다패턴,
                     헤딩번호목인가, 주헤딩인가, 불릿패턴, 러닝헤더패턴, 쪽번호패턴)

등급들 = ["a", "b", "c", "d", "e"]
허용오차_열 = 40
대괄호캡션패턴 = re.compile(r"^\[([^\[\]]{2,40})\]$")   # '[표 X]'가 아닌 '[염해에 관한 ...]'류


def _눈금(vals, tol=1.5):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _색인(g, v, tol=1.5):
    for i, x in enumerate(g):
        if abs(v - x) <= tol:
            return i
    return min(range(len(g)), key=lambda i: abs(g[i] - v))


def _글자(page, b):
    if b[2] - b[0] < 1 or b[3] - b[1] < 1:
        return ""
    try:
        t = page.crop((b[0] + .5, b[1] + .5, b[2] - .5, b[3] - .5)).extract_text(
            x_tolerance=1.5, y_tolerance=2) or ""
    except Exception:
        return ""
    return re.sub(r"\s+", " ", t).strip()


def 격자(page, tbl):
    xs = _눈금({c[0] for c in tbl.cells} | {c[2] for c in tbl.cells})
    ys = _눈금({c[1] for c in tbl.cells} | {c[3] for c in tbl.cells})
    셀들 = []
    for b in tbl.cells:
        r, c = _색인(ys, b[1]), _색인(xs, b[0])
        셀들.append({"r": r, "c": c, "rs": max(1, _색인(ys, b[3]) - r),
                     "cs": max(1, _색인(xs, b[2]) - c), "글": _글자(page, b)})
    return len(ys) - 1, len(xs) - 1, 셀들


def 표읽기(page, cfg):
    mid = page.width / 2
    결과 = []
    for tbl in page.find_tables():
        if not tbl.cells:
            continue
        행수, 열수, 셀들 = 격자(page, tbl)
        if 행수 < 2 or 열수 < 2:
            continue
        h = 헤더행수(행수, 열수, 셀들)
        경로, 행 = 펼치기(열수, 셀들, h, 행수)
        col = 0 if not cfg["이단"] else (0 if (tbl.bbox[0] + tbl.bbox[2]) / 2 < mid else 1)
        결과.append({"top": tbl.bbox[1], "left": tbl.bbox[0], "right": tbl.bbox[2],
                     "col": col, "경로": 경로, "행": 행})
    return 결과


def 표bbox들(page):
    return [tbl.bbox for tbl in page.find_tables() if tbl.cells]


def _겹침(cap, t):
    return not (cap["x1"] < t["left"] - 허용오차_열 or cap["x0"] > t["right"] + 허용오차_열)


def 병합스트림(pdf경로, cfg):
    """줄(문장)과 표를 하나의 읽기순서 스트림으로 합친다.
    표 항목은 {"kind":"table", ...펼쳐진 표...}, 줄 항목은 {"kind":"line", ...}."""
    스트림 = []
    with pdfplumber.open(pdf경로) as pdf:
        for 면번호, page in enumerate(pdf.pages, 1):
            if 면번호 in cfg["목차면"]:
                continue
            bboxes = 표bbox들(page)
            mid = page.width / 2

            버킷 = {}
            for c in page.chars:
                안 = any(c["x0"] >= bx0 - 1 and c["x1"] <= bx1 + 1
                        and c["top"] >= btop - 1 and c["bottom"] <= bbottom + 1
                        for bx0, btop, bx1, bbottom in bboxes)
                if 안:
                    continue
                col = 0 if not cfg["이단"] else (0 if (c["x0"] + c["x1"]) / 2 < mid else 1)
                버킷.setdefault((col, round(c["top"]), round(c["size"], 1)), []).append(c)

            줄들 = []
            for (col, top, size), cs in sorted(버킷.items(), key=lambda kv: (kv[0][0], kv[0][1])):
                cs = sorted(cs, key=lambda x: x["x0"])
                조각, 직전 = [], None
                for c in cs:
                    if 직전 is not None and c["x0"] - 직전["x1"] > 직전["size"] * 0.28:
                        조각.append(" ")
                    조각.append(c["text"])
                    직전 = c
                글 = 라벨정리("".join(조각).strip())
                if 글:
                    줄들.append({"kind": "line", "col": col, "top": top, "size": size,
                                "text": 글, "면": 면번호})

            표들 = [dict(t, kind="table", 면=면번호) for t in 표읽기(page, cfg)]
            for it in 줄들 + 표들:
                it.setdefault("size", None)
            스트림.extend(sorted(줄들 + 표들, key=lambda it: (it["col"], it["top"])))
    return 스트림


def 키(스트림, i):
    if i >= len(스트림):        # 마지막 절 뒤에 아무것도 없을 때(예: 1.7) 끝을 나타내는 값
        return (float("inf"), float("inf"), float("inf"))
    it = 스트림[i]
    return (it["면"], it["col"], it["top"])


def 하위절찾기(스트림, cfg, 절_상위, 다음_절_상위):
    """스트림에서 '{절_상위}.N' 하위절을 등장 순서대로 전부 찾는다.
    1.4는 하위절이 2개(1.4.1/1.4.2)지만 1.3은 3개(1.3.1~1.3.3)라서
    개수를 하드코딩하지 않고 실제 등장하는 만큼 찾는다.

    다음_절_상위가 None이면 이 절이 문서의 마지막 절이라는 뜻이다(예: 1.7
    다음엔 아무것도 없이 문서가 끝난다). 이 경우 끝 경계는 스트림 끝까지다.
    """
    하위절 = []   # [번호, 제목, 시작인덱스, 끝인덱스]
    끝인덱스 = None
    본 = set()
    접두 = re.escape(절_상위)
    소패턴 = re.compile(rf"^{접두}\.(\d+)\s*(.*)$")
    for i, it in enumerate(스트림):
        if it["kind"] != "line":
            continue
        if 분류(it["size"], cfg) == "절3":
            m = 소패턴.match(it["text"])
            if m:
                번호 = f"{절_상위}.{m.group(1)}"
                if 번호 not in 본:
                    본.add(번호)
                    하위절.append([번호, m.group(2).strip(), i])
        if 다음_절_상위 is not None and 분류(it["size"], cfg) == "절2":
            n = re.sub(r"\s+", "", it["text"])
            if 끝인덱스 is None and n.startswith(다음_절_상위):
                끝인덱스 = i
    for j in range(len(하위절) - 1):
        하위절[j].append(하위절[j + 1][2])
    if 하위절:
        하위절[-1].append(len(스트림) if 다음_절_상위 is None else 끝인덱스)
    return 하위절


def 무번호이름(현재_주, 현재_소목차, 현재_목):
    return 현재_주 or 현재_소목차 or 현재_목 or "미상"


def 파일명_무번호(이름):
    안전 = re.sub(r'[\\/:*?"<>|]', "", 이름).strip()
    return f"표_{안전}.md"


def 등급표인가(행들):
    if not 행들:
        return False
    키들 = [(r[0] or "").strip().lower() for r in 행들]
    return all(k in 등급들 for k in 키들) and len(set(키들)) >= 3


def 등급표KV(제목, 번호, 면, 경로, 행들, 연도, 절_상위, 무번호이름값=None):
    부재 = 부재명(제목) if 번호 else 제목
    if 번호:
        출처 = f"[표 {번호}] {판본}@{연도}" + (f" {면}면" if 면 else "")
        머리 = f"[표 {번호}] {제목}"
    else:
        출처 = f"{무번호이름값} {판본}@{연도}" + (f" {면}면" if 면 else "")
        머리 = 무번호이름값   # 무번호 표는 이름 자체가 이미 그 계층 제목이라 중복 표기하지 않는다
    줄 = [f"# {머리}", "",
          "문서: 시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편",
          f"판본: {판본}@{연도}", f"절: {절_상위}"]
    if 번호:
        줄.append(f"표: {번호}")
    if 면:
        줄.append(f"면: {면}")
    줄 += [f"부재: {부재}", f"평가항목수: {len(경로) - 1}", "", "평가항목:"]
    줄 += [f"- {' > '.join(p)}" for p in 경로[1:]] + [""]
    for 행 in 행들:
        등급 = (행[0] or "").strip().lower()
        if 등급 not in 등급들:
            continue
        for c in range(1, len(경로)):
            칸 = (행[c] or "").strip()
            if not 칸:
                continue
            p = 경로[c]
            줄 += ["---", "", f"## {등급}등급 · {' > '.join(p)}", "",
                   f"부재: {부재}", f"평가항목: {p[0] if p else ''}",
                   f"세부항목: {p[-1] if len(p) > 1 else ''}", f"등급: {등급}"]
            줄 += [f"기준: {x}" for x in 항목쪼개기(칸)]
            줄 += [f"출처: {출처}", ""]
    return "\n".join(줄).rstrip() + "\n"


def 일반표KV(제목, 번호, 면, 경로, 행들, 연도, 절_상위, 무번호이름값=None):
    if 번호:
        출처 = f"[표 {번호}] {판본}@{연도}" + (f" {면}면" if 면 else "")
        머리 = f"[표 {번호}] {제목}"
    else:
        출처 = f"{무번호이름값} {판본}@{연도}" + (f" {면}면" if 면 else "")
        머리 = 무번호이름값   # 무번호 표는 이름 자체가 이미 그 계층 제목이라 중복 표기하지 않는다
    줄 = [f"# {머리}", "",
          "문서: 시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편",
          f"판본: {판본}@{연도}", f"절: {절_상위}"]
    if 번호:
        줄.append(f"표: {번호}")
    if 면:
        줄.append(f"면: {면}")
    줄 += ["", "표종류: 일반(행/열)", ""]
    for i, 행 in enumerate(행들, 1):
        식별 = (행[0] or "").strip() or f"행{i}"
        줄 += ["---", "", f"## {식별}", ""]
        for c in range(len(경로)):
            값 = (행[c] or "").strip()
            if not 값:
                continue
            키표시 = " > ".join(경로[c]) if 경로[c] else (f"열{c}" if c else "구분")
            줄.append(f"{키표시}: {값}")
        줄.append(f"출처: {출처}")
        줄.append("")
    return "\n".join(줄).rstrip() + "\n"


def 무번호이름_예비스캔(구간, cfg):
    """같은 헤딩 아래 무번호 표가 여럿이면 나중에 이름이 겹친다.
    실제로 쓰기 전에 한 번 훑어 몇 번 겹치는지 세어 둔다."""
    현재_목, 현재_소목차, 현재_주 = None, None, None
    기대번호, 기대주번호, 최근캡션 = 1, 1, None
    이름들 = []
    for it in 구간:
        if it["kind"] == "table":
            if 최근캡션 is not None:
                최근캡션 = None
            else:
                이름들.append(무번호이름(현재_주, 현재_소목차, 현재_목))
            continue
        글 = it["text"]
        if 러닝헤더패턴.match(re.sub(r"\s+", "", 글)):
            continue
        계층 = 분류(it["size"], cfg)
        if 계층 == "목":
            m = 가나다패턴.match(글)
            if m:
                현재_목, 현재_소목차, 현재_주 = m.group(2).strip(), None, None
                기대번호, 기대주번호 = 1, 1
                continue
        if 계층 == "본문":
            if 쪽번호패턴.match(글):
                continue
            if 캡션패턴.match(글):
                최근캡션 = True
                continue
            bm = 대괄호캡션패턴.match(글)
            if bm and not bm.group(1).startswith(("그림", "표")):
                최근캡션 = True
                continue
            hm = 헤딩번호목인가(글, 기대번호)
            if hm is not None:
                현재_소목차, 현재_주, 기대번호, 기대주번호 = hm, None, 기대번호 + 1, 1
                continue
            jm = 주헤딩인가(글, 기대주번호)
            if jm is not None:
                현재_주, 기대주번호 = jm, 기대주번호 + 1
    return collections.Counter(이름들)


def 이미완료된번호들(표폴더):
    번호들 = set()
    if 표폴더.exists():
        for f in 표폴더.glob("표*.md"):
            m = re.match(r"표([\d.]+(?:의\d+)?)\s", f.name)
            if m:
                번호들.add(m.group(1))
    return 번호들


def 실행(pdf경로, 연도, 절폴더명, 절_상위, 절_설명, 다음_절_상위):
    """절_상위 예: '1.3' 또는 '1.4'. 다음_절_상위는 그 절이 끝나는 지점을
    찾기 위한 다음 최상위 절 번호(예: '1.3'이면 '1.4', '1.4'면 '1.5')."""
    from 공용 import 표출력뿌리, 텍스트출력뿌리 as 텍스트뿌리
    표폴더 = 표출력뿌리(절폴더명) / 연도
    텍스트폴더 = 텍스트뿌리(절폴더명) / 연도

    cfg = 문서형식감지(pdf경로)
    스트림 = 병합스트림(pdf경로, cfg)
    하위절 = 하위절찾기(스트림, cfg, 절_상위, 다음_절_상위)
    if not 하위절:
        raise RuntimeError(f"{연도}: '{절_상위}' 하위절을 못 찾음")
    if 하위절[-1][3] is None:
        raise RuntimeError(f"{연도}: '{절_상위}' 절의 끝({다음_절_상위} 시작)을 못 찾음")

    완료 = 이미완료된번호들(표폴더)
    표폴더.mkdir(parents=True, exist_ok=True)
    텍스트폴더.mkdir(parents=True, exist_ok=True)

    새표 = []
    전체출력 = [f"# {절_상위} {절_설명}", "",
              "문서: 시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편",
              f"판본: {판본}@{연도}", f"절: {절_상위}", ""]

    for 번호, 제목, 시작idx, 끝idx in 하위절:
        시작키, 끝키 = 키(스트림, 시작idx + 1), 키(스트림, 끝idx)
        구간 = [it for it in 스트림 if 시작키 <= (it["면"], it["col"], it["top"]) < 끝키]
        중복카운트 = 무번호이름_예비스캔(구간, cfg)
        순번누적 = collections.defaultdict(int)

        출력 = ["", f"## {번호} {제목}", ""]
        기대번호 = 1
        기대주번호 = 1
        현재_목, 현재_소목차, 현재_주 = None, None, None
        최근캡션 = None
        누적 = []

        def 문단flush():
            if 누적:
                출력.append("내용: " + " ".join(누적))
                누적.clear()

        for it in 구간:
            if it["kind"] == "table":
                if 최근캡션 is not None:
                    표번호, 표제목 = 최근캡션
                    최근캡션 = None
                else:
                    표번호 = None
                    표제목root = 무번호이름(현재_주, 현재_소목차, 현재_목)
                    if 중복카운트[표제목root] > 1:
                        순번누적[표제목root] += 1
                        표제목 = f"{표제목root}-{순번누적[표제목root]}"
                    else:
                        표제목 = 표제목root

                문단flush()
                if 표번호:
                    출력.append(f"표참조: 표{표번호} {표제목}")
                else:
                    출력.append(f"표참조: 표_{표제목}")

                if 표번호 and 표번호 in 완료:
                    continue  # 이미 뽑아둔 등급표 — 새로 안 만든다
                if not it["경로"] or not it["행"]:
                    continue

                if 등급표인가(it["행"]):
                    본 = 등급표KV(표제목 or "", 표번호, it["면"], it["경로"], it["행"], 연도, 절_상위,
                                 None if 표번호 else f"표_{표제목}")
                else:
                    본 = 일반표KV(표제목 or "", 표번호, it["면"], it["경로"], it["행"], 연도, 절_상위,
                                 None if 표번호 else f"표_{표제목}")
                f이름 = 파일명_등급표(표번호, 표제목) if 표번호 else 파일명_무번호(표제목)
                (표폴더 / f이름).write_text(본, encoding="utf-8")
                if 표번호:
                    완료.add(표번호)
                새표.append((연도, f이름))
                continue

            # ---- 줄(문장) 처리 ----
            글 = it["text"]
            if 러닝헤더패턴.match(re.sub(r"\s+", "", 글)):
                continue
            계층 = 분류(it["size"], cfg)

            if 계층 == "목":
                m = 가나다패턴.match(글)
                if m:
                    문단flush()
                    출력 += ["", f"### {m.group(1)}. {m.group(2).strip()}", ""]
                    현재_목 = m.group(2).strip()
                    현재_소목차, 현재_주 = None, None
                    기대번호 = 1
                    기대주번호 = 1
                    continue

            if 계층 == "본문":
                if 쪽번호패턴.match(글):
                    continue
                cm = 캡션패턴.match(글)
                if cm:
                    최근캡션 = (cm.group(1), cm.group(2).strip())
                    continue
                bm = 대괄호캡션패턴.match(글)
                if bm and not bm.group(1).startswith(("그림", "표")):
                    최근캡션 = (None, bm.group(1))
                    continue
                hm = 헤딩번호목인가(글, 기대번호)
                if hm is not None:
                    문단flush()
                    출력 += ["", f"#### {기대번호}) {hm}", ""]
                    현재_소목차, 현재_주 = hm, None
                    기대번호 += 1
                    기대주번호 = 1
                    continue
                jm = 주헤딩인가(글, 기대주번호)
                if jm is not None:
                    문단flush()
                    출력 += ["", f"##### 주{기대주번호}) {jm}", ""]
                    현재_주 = jm
                    기대주번호 += 1
                    continue
                if 불릿패턴.match(글):
                    문단flush()
                누적.append(글)
                continue

        문단flush()
        전체출력.extend(출력)

    파일명 = f"{절_상위} {절_설명}.md"
    (텍스트폴더 / 파일명).write_text("\n".join(전체출력).rstrip() + "\n", encoding="utf-8")
    for 번호, 제목, *_ in 하위절:      # 예전에 절별로 파일을 나눠 만들었던 산출물이 있으면 정리
        옛경로 = 텍스트폴더 / f"{번호} {제목}.md"
        if 옛경로.exists() and 옛경로.name != 파일명:
            옛경로.unlink()

    return 새표
