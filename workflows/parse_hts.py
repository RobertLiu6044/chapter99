"""
Part 2 — parse scraped payloads into Postgres.

Reads JSON under data/ only (never writes there, never hits the network).
Idempotent: clears parsed tables, then re-inserts from the current files.
"""

from __future__ import annotations

import json
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
from hatchet_sdk import Context
from pydantic import BaseModel

from client import hatchet
from hts_util import (
    extract_excludes,
    extract_note_ref,
    extract_references,
    is_superior,
    parse_hts_code,
    parse_rule_rate,
    parse_special_rates,
    subchapter_for,
    walk_with_inherited_mfn,
)

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://postgres:postgres@localhost:5432/chp99",
)


class ParseInput(BaseModel):
    pass


class ParseCount(BaseModel):
    rows: int
    specials: int = 0


class ParseSummary(BaseModel):
    hts_base: int
    rules: int
    edges: int
    special_base: int
    special_rule: int


parse_workflow = hatchet.workflow(
    name="Parse",
    input_validator=ParseInput,
)


def _connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def _read_json(name: str) -> list[dict]:
    path = DATA_DIR / name
    # Read-only on data/: open for reading only; never write under DATA_DIR.
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{name} is not a JSON array")
    return data


@parse_workflow.task(
    execution_timeout=timedelta(minutes=2),
    retries=2,
)
def clear_parsed(input: ParseInput, ctx: Context) -> ParseCount:
    """Wipe parsed tables so a re-run replaces rows instead of duplicating."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE special_rule, special_base, rule_edge, rule, hts_base"
            )
        conn.commit()
    ctx.log("truncated special_rule, special_base, rule_edge, rule, hts_base")
    return ParseCount(rows=0, specials=0)


@parse_workflow.task(
    parents=[clear_parsed],
    execution_timeout=timedelta(minutes=15),
    retries=2,
)
def load_hts_base(input: ParseInput, ctx: Context) -> ParseCount:
    rows = _read_json("chapters_1_97.json")
    ctx.log(f"read chapters_1_97.json ({len(rows)} rows)")

    batch: list[tuple] = []
    specials: list[tuple] = []
    seen: set[str] = set()
    inherited = 0
    superiors = 0
    # Synthetic codes for superior rows (empty htsno): (0, n, -1, -1).
    # h0=0 is outside real chapters 1–97, so it never collides with schedule codes.
    sup_seq = 0
    # Nearest coded ancestor by indent, for readable synthetic hts labels.
    coded_stack: list[tuple[int, str]] = []
    # Indent stack of resolved special-rate lists (own or inherited).
    special_stack: list[tuple[int, list[tuple[str, Decimal, str]]]] = []

    # Walk every row so the indent stack stays aligned with the schedule tree.
    for row, rate, unit in walk_with_inherited_mfn(rows):
        indent = int(row.get("indent") or 0)
        while coded_stack and coded_stack[-1][0] >= indent:
            coded_stack.pop()
        while special_stack and special_stack[-1][0] >= indent:
            special_stack.pop()

        own_special = (row.get("special") or "").strip()
        if own_special:
            specs = parse_special_rates(own_special)
        elif special_stack:
            specs = special_stack[-1][1]
        else:
            specs = []
        special_stack.append((indent, specs))

        hts = (row.get("htsno") or "").strip()
        code = parse_hts_code(hts)
        row_is_superior = is_superior(row.get("superior") or "")

        if code is None:
            # In chapters_1_97 every empty-htsno row is superior; still guard.
            if not row_is_superior:
                continue
            sup_seq += 1
            parent = coded_stack[-1][1] if coded_stack else "root"
            hts = f"sup:{parent}:{sup_seq:05d}"
            code = (0, sup_seq, -1, -1)
            # Superiors are labels, not duty lines — do not store a tariff.
            rate, unit = None, None
            superiors += 1
            store_specials = False
        else:
            if hts in seen:
                continue
            seen.add(hts)
            coded_stack.append((indent, hts))
            if not (row.get("general") or "").strip() and (
                rate is not None or unit is not None
            ):
                inherited += 1
            store_specials = True

        h0, h1, h2, h3 = code
        batch.append(
            (
                h0,
                h1,
                h2,
                h3,
                hts,
                row_is_superior,
                row.get("description") or "",
                rate,
                unit,
            )
        )
        if store_specials:
            for tag, srate, sunit in specs:
                specials.append((h0, h1, h2, h3, tag, srate, sunit))

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO hts_base (code, hts, superior, description, mfn_rate, mfn_rate_unit)
                VALUES (ROW(%s, %s, %s, %s)::hts_code, %s, %s, %s, %s, %s)
                ON CONFLICT (hts) DO UPDATE SET
                  superior = EXCLUDED.superior,
                  description = EXCLUDED.description,
                  mfn_rate = EXCLUDED.mfn_rate,
                  mfn_rate_unit = EXCLUDED.mfn_rate_unit
                """,
                batch,
            )
            cur.executemany(
                """
                INSERT INTO special_base
                  (hts_code, special_tag, special_rate, special_rate_unit)
                VALUES (ROW(%s, %s, %s, %s)::hts_code, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                specials,
            )
        conn.commit()

    ctx.log(
        f"inserted {len(batch)} hts_base rows "
        f"({superiors} superior, {inherited} inherited rates); "
        f"special_base={len(specials)}"
    )
    return ParseCount(rows=len(batch), specials=len(specials))


@parse_workflow.task(
    parents=[load_hts_base],
    execution_timeout=timedelta(minutes=15),
    retries=2,
)
def load_rules(input: ParseInput, ctx: Context) -> ParseSummary:
    rows = _read_json("chapter99.json")
    ctx.log(f"read chapter99.json ({len(rows)} rows)")

    rules: list[tuple] = []
    edges: list[tuple] = []
    specials: list[tuple] = []
    seen_rules: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    seen_special: set[tuple[str, str, str]] = set()

    for row in rows:
        hts = (row.get("htsno") or "").strip()
        code = parse_hts_code(hts)
        if code is None or hts in seen_rules:
            continue
        seen_rules.add(hts)

        description = row.get("description") or ""
        rate_kind, rate_value, rate_unit = parse_rule_rate(row.get("general") or "")
        note_ref = extract_note_ref(description)
        h0, h1, h2, h3 = code

        rules.append(
            (
                h0,
                h1,
                h2,
                h3,
                hts,
                subchapter_for(hts),
                description,
                rate_kind,
                rate_value,
                rate_unit,
                note_ref,
            )
        )

        for target in extract_references(description):
            tcode = parse_hts_code(target)
            if tcode is None:
                continue
            key = (hts, "references", target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            t0, t1, t2, t3 = tcode
            edges.append((h0, h1, h2, h3, "references", t0, t1, t2, t3))

        for target in extract_excludes(description):
            tcode = parse_hts_code(target)
            if tcode is None or target == hts:
                continue
            key = (hts, "excludes", target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            t0, t1, t2, t3 = tcode
            edges.append((h0, h1, h2, h3, "excludes", t0, t1, t2, t3))

        for tag, srate, sunit in parse_special_rates(row.get("special") or ""):
            key = (hts, tag, sunit)
            if key in seen_special:
                continue
            seen_special.add(key)
            specials.append((h0, h1, h2, h3, tag, srate, sunit))

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO rule
                  (code, hts, subchapter, description, rate_kind, rate_value, rate_unit, note_ref)
                VALUES (ROW(%s, %s, %s, %s)::hts_code, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (hts) DO UPDATE SET
                  subchapter = EXCLUDED.subchapter,
                  description = EXCLUDED.description,
                  rate_kind = EXCLUDED.rate_kind,
                  rate_value = EXCLUDED.rate_value,
                  rate_unit = EXCLUDED.rate_unit,
                  note_ref = EXCLUDED.note_ref
                """,
                rules,
            )
            cur.executemany(
                """
                INSERT INTO rule_edge (source_hts, edge_type, target_hts)
                VALUES (
                  ROW(%s, %s, %s, %s)::hts_code,
                  %s,
                  ROW(%s, %s, %s, %s)::hts_code
                )
                ON CONFLICT DO NOTHING
                """,
                edges,
            )
            cur.executemany(
                """
                INSERT INTO special_rule
                  (rule_code, special_tag, special_rate, special_rate_unit)
                VALUES (ROW(%s, %s, %s, %s)::hts_code, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                specials,
            )
        conn.commit()

    ctx.log(
        f"inserted rules={len(rules)} edges={len(edges)} "
        f"special_rule={len(specials)}"
    )
    return ParseSummary(
        hts_base=ctx.task_output(load_hts_base).rows,
        rules=len(rules),
        edges=len(edges),
        special_base=ctx.task_output(load_hts_base).specials,
        special_rule=len(specials),
    )
