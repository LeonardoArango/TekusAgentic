"""Chunking semántico simple: por encabezados Markdown, con límite de tamaño.

No reimplementa nada exótico — corta por headings (##, ###) y subdivide un
heading si su contenido supera max_chars, para no romper la coherencia
semántica dentro de un fragmento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str


def chunk_markdown(text: str, max_chars: int = 1200) -> list[Chunk]:
    text = text.strip()
    if not text:
        return []

    boundaries = [m.start() for m in _HEADING_RE.finditer(text)]
    if not boundaries or boundaries[0] != 0:
        boundaries = [0, *boundaries]
    boundaries.append(len(text))

    sections = [
        text[boundaries[i] : boundaries[i + 1]].strip()
        for i in range(len(boundaries) - 1)
        if text[boundaries[i] : boundaries[i + 1]].strip()
    ]

    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
            continue
        for i in range(0, len(section), max_chars):
            chunks.append(section[i : i + max_chars])

    return [Chunk(index=i, text=c) for i, c in enumerate(chunks)]
