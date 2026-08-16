"""Database helpers for the Part 3 API. Read-only against existing tables."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://postgres:postgres@localhost:5432/chp99",
)


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def code_tuple(row: dict[str, Any]) -> tuple[int, int, int, int]:
    """Normalize a composite `code` column into a 4-int tuple."""
    c = row["code"]
    if isinstance(c, (list, tuple)):
        return int(c[0]), int(c[1]), int(c[2]), int(c[3])
    # psycopg may return a string like "(101,21,0,10)" or a custom object
    if hasattr(c, "h0"):
        return int(c.h0), int(c.h1), int(c.h2), int(c.h3)
    s = str(c).strip("()")
    parts = [int(p.strip()) for p in s.split(",")]
    return parts[0], parts[1], parts[2], parts[3]


def format_code(code: tuple[int, int, int, int]) -> str:
    h0, h1, h2, h3 = code
    if h0 == 0:
        return f"sup:{h1}"
    s = f"{h0:04d}"
    if h1 >= 0:
        s += f".{h1:02d}"
    if h2 >= 0:
        s += f".{h2:02d}"
    if h3 >= 0:
        s += f".{h3:02d}"
    return s


def ancestors(code: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    """Strict ancestors of a coded HTS line, nearest parent last."""
    if code[0] == 0:
        return []
    h0, h1, h2, h3 = code
    segs = [h0, h1, h2, h3]
    out: list[tuple[int, int, int, int]] = []
    for depth in range(3, 0, -1):
        if segs[depth] < 0:
            continue
        truncated = segs[:depth] + [-1] * (4 - depth)
        out.append((truncated[0], truncated[1], truncated[2], truncated[3]))
    out.reverse()  # root → nearest parent
    return out


def is_prefix(
    parent: tuple[int, int, int, int], child: tuple[int, int, int, int]
) -> bool:
    for i in range(4):
        if parent[i] == -1:
            return True
        if parent[i] != child[i]:
            return False
    return True
