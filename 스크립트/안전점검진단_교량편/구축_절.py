# -*- coding: utf-8 -*-
"""임의의 절(1.3, 1.4, ...) 안의 표+본문을 뽑는 공용 러너.

대상 연도를 하드코딩하지 않는다 — 원본폴더 밑에 '20XX ...' 형태의 폴더가
새로 생기면(예: 2027년 지침이 나와서 폴더가 추가되면) 그 안의 PDF를 자동으로
찾아서 같이 처리한다. 연도가 늘어나도 이 파일이나 구축_1.N.py를 고칠 필요가
없다.

절마다 개별 구축_*.py 스크립트(구축_1.3.py, 구축_1.4.py)가 이 함수를 부른다.
"""
import re
import 추출_전체표
from 공용 import 원본폴더

연도폴더패턴 = re.compile(r"^(\d{4})")


def 판본목록():
    """원본폴더 밑의 모든 '20XX...' 폴더를 훑어, 안전점검·진단 교량편 PDF를 찾는다.
    HWP만 있고 PDF가 없는 연도(아직 변환 안 됐거나 배포용 문서로 막힌 경우)는
    (연도, None)으로 반환해 실행() 쪽에서 건너뛰게 한다."""
    out = []
    if not 원본폴더.exists():
        return out
    연도폴더들 = sorted(
        (d for d in 원본폴더.iterdir() if d.is_dir() and 연도폴더패턴.match(d.name)),
        key=lambda d: d.name,
    )
    for 폴더 in 연도폴더들:
        연도 = 연도폴더패턴.match(폴더.name).group(1)
        후보 = [f for f in sorted(폴더.glob("*.pdf"))
                if f.name.startswith("01.") and "안전점검" in f.name and "교량편" in f.name]
        out.append((연도, 후보[0] if 후보 else None))
    return out


def 실행(절폴더명, 절_상위, 절_설명, 다음_절_상위):
    for 연도, pdf경로 in 판본목록():
        if pdf경로 is None:
            print(f"[{연도}] 파일 없음 — 건너뜀")
            continue
        새표 = 추출_전체표.실행(pdf경로, 연도, 절폴더명, 절_상위, 절_설명, 다음_절_상위)
        print(f"[{연도}] 새로 만든 표 {len(새표)}개")
        for _, 이름 in 새표:
            print(f"    {이름}")
