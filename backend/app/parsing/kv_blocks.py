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
