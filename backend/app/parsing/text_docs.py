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
