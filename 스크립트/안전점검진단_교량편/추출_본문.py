# -*- coding: utf-8 -*-
"""1.4 상태평가기준 및 방법의 서술형 본문(표 제외)을 Markdown-KV로 뽑는다.

표 안의 글자는 모두 제외하고, 표가 있던 자리에는 "표참조:"로 원문 표
번호와 원문 캡션만 남긴다. 표 내용 자체는 표_부재별_상태평가기준/에
이미 있으므로 여기서는 다시 담지 않는다.

일부 연도는 한글이 SaveAs 하면서 좌우 2단 레이아웃으로 압축되고 글자 크기도
약 0.71배로 줄어 있다(예: 2023·2024). 이걸 연도별로 하드코딩해 두지 않고,
PDF 파일 자체를 열어서 판정한다 — 새 연도 PDF가 추가돼도 코드를 안 고쳐도
된다(문서형식감지 참고). 열 구분은 문자 하나하나의 x좌표가 페이지 폭
절반의 어느 쪽인지로 가른다 — 좌우 캡션이 같은 높이에서 한 줄로 겹쳐
보이는 문제(표 추출 때 겪은 문제)가 애초에 생기지 않는다.
"""
import functools
import re
import pdfplumber
from 공용 import 라벨정리, 원본폴더, 판본

기준크기 = {"절2": 20.0, "절3": 15.0, "목": 13.0, "본문": 11.0}
허용오차 = 0.25


@functools.lru_cache(maxsize=None)
def 문서형식감지(pdf경로):
    """PDF 자체를 검사해 배율·2단 여부·목차 페이지 수를 판정한다.

    - 2단/배율: 첫 면이 가로형(폭>높이)이면 한글이 압축 출력한 문서로 보고
      0.71배·2단으로 판정한다. 세로형이면 원본 그대로(1.0배·단일열)다.
    - 목차 페이지 수: 절2 크기의 '1.1'이 여러 번 나올 수 있는데(대목차·소목차
      목차 페이지에도 나온다), 그중 바로 다음에 나오는 헤딩이 '1.1.1'인
      경우가 실제 본문 시작이다. 그 앞 페이지는 전부 목차로 보고 건너뛴다.
    """
    pdf경로 = str(pdf경로)
    with pdfplumber.open(pdf경로) as pdf:
        첫면 = pdf.pages[0]
        이단 = 첫면.width > 첫면.height
        scale = 0.71 if 이단 else 1.00
        목차면 = _목차면판정(pdf, scale)
    return {"scale": scale, "이단": 이단, "목차면": 목차면}


def _목차면판정(pdf, scale):
    헤딩스트림 = []
    for i, pg in enumerate(pdf.pages, 1):
        버킷 = {}
        for c in pg.chars:
            버킷.setdefault((round(c["top"]), round(c["size"], 1)), []).append(c)
        for (top, size), cs in sorted(버킷.items()):
            if not (abs(size - 20.0 * scale) <= 허용오차 or abs(size - 15.0 * scale) <= 허용오차):
                continue
            cs = sorted(cs, key=lambda x: x["x0"])
            txt = "".join(c["text"] for c in cs).strip()
            n = re.sub(r"\s+", "", txt)
            if re.match(r"^\d+\.\d+(\.\d+)?[가-힣(]", n) or re.match(r"^\d+\.\d+(\.\d+)?$", n):
                헤딩스트림.append((i, n))
    for idx, (면, n) in enumerate(헤딩스트림):
        if re.match(r"^1\.1(?!\d|\.)", n) and idx + 1 < len(헤딩스트림):
            if 헤딩스트림[idx + 1][1].startswith("1.1.1"):
                return set(range(1, 면))
    return set()   # 못 찾으면 목차 스킵 없이 안전하게 진행

캡션패턴 = re.compile(r"^\[표\s*([\d.]+(?:의\d+)?)\]\s*(.+)$")
가나다패턴 = re.compile(r"^([가-힣])\.\s*(.+)$")
번호목패턴 = re.compile(r"^(\d{1,3})\)\s*(.+)$")
주목패턴 = re.compile(r"^주(\d{1,2})\)\s*(.+)$")     # '주1) 균열률 산정 방법' 같은 각주 계층
러닝헤더패턴 = re.compile(r"^1\.4\.\d[가-힣]\.")   # 페이지 여백에 반복 출력되는 위치표시
쪽번호패턴 = re.compile(r"^\d+-\d+$")               # 예: '1-50' 같은 쪽번호(장-면)
불릿패턴 = re.compile(r"^[◦○◯▷■￭]")               # 글머리표 — 여기서 새 '내용:' 항목이 시작된다


def 근접(size, 이름, cfg):
    return abs(size - 기준크기[이름] * cfg["scale"]) <= 허용오차


def 분류(size, cfg):
    """줄의 글자 크기로 계층을 가른다.

    본문 표준 크기(11.0)보다 작은 10.0pt짜리 '< 해 설 >' 보충설명도 실제
    있어, 절/목 표제 크기에 안 걸리면 전부 본문으로 본다. 다만 각주
    위첨자(5~6pt대)는 문장이 아니라 참조번호일 뿐이므로 제외한다.
    """
    if 근접(size, "절2", cfg):
        return "절2"
    if 근접(size, "절3", cfg):
        return "절3"
    if 근접(size, "목", cfg):
        return "목"
    if size >= 8.0 * cfg["scale"] - 허용오차:
        return "본문"
    return None


def 표bbox들(page):
    return [tbl.bbox for tbl in page.find_tables() if tbl.cells]


def 표안인가(x0, x1, top, bottom, bboxes):
    for bx0, btop, bx1, bbottom in bboxes:
        if x0 >= bx0 - 1 and x1 <= bx1 + 1 and top >= btop - 1 and bottom <= bbottom + 1:
            return True
    return False


def 줄목록(page, cfg):
    """표 안의 글자를 뺀 나머지 글자를 (열, 세로위치)로 묶어 읽는 순서로 낸다."""
    bboxes = 표bbox들(page)
    mid = page.width / 2
    버킷 = {}
    for c in page.chars:
        if 표안인가(c["x0"], c["x1"], c["top"], c["bottom"], bboxes):
            continue
        col = 0 if not cfg["이단"] else (0 if (c["x0"] + c["x1"]) / 2 < mid else 1)
        버킷.setdefault((col, round(c["top"]), round(c["size"], 1)), []).append(c)

    결과 = []
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
            결과.append({"col": col, "top": top, "size": size, "text": 글})
    return 결과


def 전체줄스트림(pdf경로, cfg):
    """문서 전체를 (면, 열, top) 순서로 읽어 하나의 줄 스트림으로 만든다."""
    스트림 = []
    with pdfplumber.open(pdf경로) as pdf:
        for 면번호, page in enumerate(pdf.pages, 1):
            if 면번호 in cfg["목차면"]:
                continue
            for 줄 in 줄목록(page, cfg):
                줄["면"] = 면번호
                스트림.append(줄)
    return 스트림


def 헤딩번호목인가(글, 기대번호):
    """'1) 콘크리트 바닥판'처럼 짧고 서술어로 안 끝나는 줄만 소목차로 본다."""
    m = 번호목패턴.match(글)
    if not m or int(m.group(1)) != 기대번호:
        return None
    본문부 = m.group(2).strip()
    if 불릿패턴.match(본문부):
        return None
    # 헤딩(짧은 명사구)은 마침표로 끝나지 않는다. 문장(서술어)은 마침표로 끝난다.
    # ('신축이음'처럼 명사가 우연히 서술어 어미와 같은 글자로 끝나는 경우를
    #  오판하지 않기 위해 어미가 아니라 마침표 유무로만 가른다.)
    if len(본문부) > 34 or 본문부.endswith("."):
        return None
    return 본문부


def 주헤딩인가(글, 기대번호):
    """'주1) 균열률 산정 방법'처럼 소목차 하위의 각주 계층을 가른다."""
    m = 주목패턴.match(글)
    if not m or int(m.group(1)) != 기대번호:
        return None
    본문부 = m.group(2).strip()
    if len(본문부) > 34 or 본문부.endswith("."):
        return None
    return 본문부
