# -*- coding: utf-8 -*-
"""표 추출이 공유하는 규칙. 이 파일 하나로 헤더 판정·라벨 정리·KV 블록 생성을 담당한다."""
import re
import pathlib

루트 = pathlib.Path(__file__).resolve().parents[2]   # .../연구_1/스크립트/안전점검진단_교량편/공용.py → 연구_1
원본폴더 = 루트 / "시설물의 안전 및 유지관리 세부지침.pdf"
데이터뿌리 = 루트 / "data" / "안전점검진단_교량편"
판본 = "안전점검진단_교량"


def 절폴더(절폴더명):
    return 데이터뿌리 / 절폴더명


def 표출력뿌리(절폴더명):
    return 절폴더(절폴더명) / "table"


def 텍스트출력뿌리(절폴더명):
    return 절폴더(절폴더명) / "text"


def 라벨정리(s):
    """PDF 자간으로 벌어진 낱글자를 붙인다. '균 열'→'균열'.
    '강 바닥판'처럼 실제 띄어쓰기는 한쪽이 2글자 이상이라 건드리지 않는다."""
    나온 = []
    for t in (s or "").strip().split(" "):
        핵 = re.sub(r"\d*\)$", "", t)
        if 나온 and len(re.sub(r"\d*\)$", "", 나온[-1])) == 1 and len(핵) == 1 \
           and re.match(r"^[가-힣]", 나온[-1]) and re.match(r"^[가-힣]", t):
            나온[-1] += t
        else:
            나온.append(t)
    return " ".join(나온)


def 항목쪼개기(칸):
    """한 칸에 ◦ 항목이 여러 개면 각각이 별개 기준이다."""
    항목 = [x.strip(" ·") for x in re.split(r"[◦○](?=\s*\S)", 칸 or "") if x.strip(" ·")]
    return 항목 or ([칸.strip()] if (칸 or "").strip() else [])


def 헤더행수(행수, 열수, 셀들):
    """데이터 행은 전체 너비를 채운다. 하위 헤더 행은 위 병합 셀 안쪽에만 있다."""
    행별 = {}
    for s in 셀들:
        행별.setdefault(s["r"], []).append(s)
    h = 1
    while h < 행수:
        위병합 = [(s["c"], s["c"] + s["cs"]) for s in 행별.get(h - 1, []) if s["cs"] > 1]
        내셀 = 행별.get(h, [])
        if not 위병합 or not 내셀 or sum(s["cs"] for s in 내셀) >= 열수:
            break
        if not all(any(a <= s["c"] and s["c"] + s["cs"] <= b for a, b in 위병합) for s in 내셀):
            break
        h += 1
    for s in 셀들:
        if s["r"] < h:
            h = max(h, s["r"] + s["rs"])
    return min(h, 행수 - 1) if 행수 > 1 else 1


def 펼치기(열수, 셀들, h, 행수):
    """헤더는 위에서 아래로 상속해 컬럼 경로를, 본문은 병합을 편 격자를 만든다."""
    머리, 몸 = {}, {}
    for s in 셀들:
        for r in range(s["r"], s["r"] + s["rs"]):
            for c in range(s["c"], s["c"] + s["cs"]):
                (머리 if r < h else 몸)[(r, c)] = s["글"]
    경로 = []
    for c in range(열수):
        칸, 직전 = [], None
        for r in range(h):
            g = 라벨정리((머리.get((r, c)) or "").strip())
            if g and g != 직전:
                칸.append(g)
                직전 = g
        경로.append(칸)
    행 = [[(몸.get((r, c)) or "") for c in range(열수)] for r in range(h, 행수)]
    return 경로, [x for x in 행 if any(x)]


def 부재명(캡션):
    """'[표 1.11의2] 콘크리트 바닥판 상세조사 상태평가기준' → '콘크리트 바닥판 상세조사'."""
    s = re.sub(r"^\s*\[표\s*[\d.]+(?:의\d+)?\]\s*", "", 캡션 or "")
    return re.sub(r"\s*상태평가기준.*$", "", s).strip()


def 파일명(번호, 제목):
    """원문 표 번호 + 원문 제목 전체를 파일명으로 쓴다.
    예: 표1.11 콘크리트 바닥판 상태평가기준.md"""
    이름 = f"표{번호} {제목}".strip()
    이름 = re.sub(r'[\\/:*?"<>|]', "", 이름)
    return f"{이름}.md"


def 블록만들기(제목, 번호, 면, 경로, 행들, 연도):
    """(등급 × 평가항목) 단위 KV 블록으로 쪼갠다. 컬럼 정렬에 의존하지 않는다."""
    부재 = 부재명(제목)
    출처 = f"[표 {번호}] {판본}@{연도}" + (f" {면}면" if 면 else "")
    줄 = [f"# [표 {번호}] {제목}", "",
          "문서: 시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편",
          f"판본: {판본}@{연도}", "절: 1.4 상태평가기준 및 방법",
          f"표: {번호}"]
    if 면:
        줄.append(f"면: {면}")
    줄 += [f"부재: {부재}", f"평가항목수: {len(경로) - 1}", "", "평가항목:"]
    줄 += [f"- {' > '.join(p)}" for p in 경로[1:]] + [""]
    for 행 in 행들:
        등급 = (행[0] or "").strip().lower()
        if 등급 not in list("abcde"):
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
