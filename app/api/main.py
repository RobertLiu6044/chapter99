"""
Part 3 API — search the base schedule and explore its Chapter 99 graph.

Reads existing tables only. No writes, no derived/materialized tables.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from db import ancestors, code_tuple, connect, format_code

app = FastAPI(title="Chapter 99 Explorer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize_hts(row: dict[str, Any]) -> dict[str, Any]:
    code = code_tuple(row)
    return {
        "hts": row["hts"],
        "code": list(code),
        "superior": bool(row.get("superior")),
        "description": row.get("description") or "",
        "mfn_rate": float(row["mfn_rate"]) if row.get("mfn_rate") is not None else None,
        "mfn_rate_unit": row.get("mfn_rate_unit"),
    }


def _serialize_rule(row: dict[str, Any]) -> dict[str, Any]:
    code = code_tuple(row)
    return {
        "hts": row["hts"],
        "code": list(code),
        "subchapter": row.get("subchapter") or "",
        "description": row.get("description") or "",
        "rate_kind": row.get("rate_kind"),
        "rate_value": float(row["rate_value"]) if row.get("rate_value") is not None else None,
        "rate_unit": row.get("rate_unit"),
        "note_ref": row.get("note_ref"),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    """Search chapters 1–97 by HTS prefix or description (trigram + ILIKE)."""
    query = q.strip()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT hts, code, superior, description, mfn_rate, mfn_rate_unit
                FROM hts_base
                WHERE hts ILIKE %s
                   OR description ILIKE %s
                   OR description %% %s
                ORDER BY
                  CASE WHEN hts ILIKE %s THEN 0 ELSE 1 END,
                  CASE WHEN superior THEN 1 ELSE 0 END,
                  similarity(COALESCE(description, ''), %s) DESC NULLS LAST,
                  hts
                LIMIT %s
                """,
                (
                    f"{query}%",
                    f"%{query}%",
                    query,
                    f"{query}%",
                    query,
                    limit,
                ),
            )
            rows = cur.fetchall()
    return {"query": query, "results": [_serialize_hts(r) for r in rows]}


@app.get("/api/hts/{hts}")
def hts_detail(hts: str) -> dict[str, Any]:
    """Base-schedule row with parent/child hierarchy and resolved Chapter 99 graph."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT hts, code, superior, description, mfn_rate, mfn_rate_unit
                FROM hts_base
                WHERE hts = %s
                """,
                (hts,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"HTS {hts!r} not found")

            selected = _serialize_hts(row)
            code = code_tuple(row)

            parents = _load_parents(cur, code)
            children = _load_children(cur, code)
            chapter99 = _resolve_chapter99_graph(cur, code, parents)

    return {
        "selected": selected,
        "parents": parents,
        "children": children,
        "chapter99": chapter99,
    }


def _load_parents(cur, code: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    chain = ancestors(code)
    if not chain:
        return []
    out: list[dict[str, Any]] = []
    for anc in chain:
        cur.execute(
            """
            SELECT hts, code, superior, description, mfn_rate, mfn_rate_unit
            FROM hts_base
            WHERE (code).h0 = %s AND (code).h1 = %s
              AND (code).h2 = %s AND (code).h3 = %s
            """,
            anc,
        )
        found = cur.fetchone()
        if found:
            out.append(_serialize_hts(found))
    return out


def _load_children(cur, code: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    """Direct children only — one segment deeper than `code`."""
    h0, h1, h2, h3 = code
    if h0 == 0 or h3 >= 0:
        return []

    if h2 >= 0:
        cur.execute(
            """
            SELECT hts, code, superior, description, mfn_rate, mfn_rate_unit
            FROM hts_base
            WHERE (code).h0 = %s AND (code).h1 = %s AND (code).h2 = %s
              AND (code).h3 >= 0
            ORDER BY (code).h3, hts
            LIMIT 200
            """,
            (h0, h1, h2),
        )
    elif h1 >= 0:
        cur.execute(
            """
            SELECT hts, code, superior, description, mfn_rate, mfn_rate_unit
            FROM hts_base
            WHERE (code).h0 = %s AND (code).h1 = %s
              AND (code).h2 >= 0 AND (code).h3 = -1
            ORDER BY (code).h2, hts
            LIMIT 200
            """,
            (h0, h1),
        )
    else:
        cur.execute(
            """
            SELECT hts, code, superior, description, mfn_rate, mfn_rate_unit
            FROM hts_base
            WHERE (code).h0 = %s AND (code).h1 >= 0
              AND (code).h2 = -1 AND (code).h3 = -1
            ORDER BY (code).h1, hts
            LIMIT 200
            """,
            (h0,),
        )

    return [_serialize_hts(r) for r in cur.fetchall()]


def _resolve_chapter99_graph(
    cur,
    selected: tuple[int, int, int, int],
    parents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rules that reference this line (or an ancestor), then full Ch99 edge closure."""
    # Codes a "references" edge may name when talking about this line.
    relevant_targets = [selected, *[tuple(p["code"]) for p in parents]]

    seed_hts: set[str] = set()
    seed_edges: list[dict[str, Any]] = []

    for target in relevant_targets:
        cur.execute(
            """
            SELECT e.edge_type,
                   (e.source_hts).h0 AS s0, (e.source_hts).h1 AS s1,
                   (e.source_hts).h2 AS s2, (e.source_hts).h3 AS s3,
                   (e.target_hts).h0 AS t0, (e.target_hts).h1 AS t1,
                   (e.target_hts).h2 AS t2, (e.target_hts).h3 AS t3,
                   r.hts AS source_hts_text
            FROM rule_edge e
            JOIN rule r
              ON (r.code).h0 = (e.source_hts).h0
             AND (r.code).h1 = (e.source_hts).h1
             AND (r.code).h2 = (e.source_hts).h2
             AND (r.code).h3 = (e.source_hts).h3
            WHERE e.edge_type = 'references'
              AND (e.target_hts).h0 = %s AND (e.target_hts).h1 = %s
              AND (e.target_hts).h2 = %s AND (e.target_hts).h3 = %s
            """,
            target,
        )
        for edge in cur.fetchall():
            seed_hts.add(edge["source_hts_text"])
            seed_edges.append(
                {
                    "source": edge["source_hts_text"],
                    "target": format_code(
                        (edge["t0"], edge["t1"], edge["t2"], edge["t3"])
                    ),
                    "edge_type": "references",
                }
            )

    if not seed_hts:
        return {"rules": [], "edges": [], "focus": []}

    # Load every rule_edge once; resolve the undirected Ch99 component in memory.
    cur.execute(
        """
        SELECT e.edge_type,
               rs.hts AS source_hts,
               (e.target_hts).h0 AS t0, (e.target_hts).h1 AS t1,
               (e.target_hts).h2 AS t2, (e.target_hts).h3 AS t3
        FROM rule_edge e
        JOIN rule rs
          ON (rs.code).h0 = (e.source_hts).h0
         AND (rs.code).h1 = (e.source_hts).h1
         AND (rs.code).h2 = (e.source_hts).h2
         AND (rs.code).h3 = (e.source_hts).h3
        """
    )
    all_edges = cur.fetchall()

    cur.execute(
        """
        SELECT hts, code, subchapter, description, rate_kind, rate_value, rate_unit, note_ref
        FROM rule
        """
    )
    rules_by_hts = {r["hts"]: r for r in cur.fetchall()}
    rule_codes = {hts: code_tuple(r) for hts, r in rules_by_hts.items()}
    code_to_hts = {code: hts for hts, code in rule_codes.items()}

    # Adjacency among Chapter 99 headings only (excludes + references-to-rules).
    adj: dict[str, set[str]] = {hts: set() for hts in rules_by_hts}
    edge_records: list[dict[str, Any]] = []

    for e in all_edges:
        src = e["source_hts"]
        tgt_code = (e["t0"], e["t1"], e["t2"], e["t3"])
        tgt_hts = code_to_hts.get(tgt_code)
        tgt_label = tgt_hts if tgt_hts else format_code(tgt_code)
        edge_records.append(
            {"source": src, "target": tgt_label, "edge_type": e["edge_type"]}
        )
        if tgt_hts:
            adj[src].add(tgt_hts)
            adj[tgt_hts].add(src)

    # BFS from seed rules across the Ch99 adjacency.
    seen: set[str] = set()
    queue = list(seed_hts)
    while queue:
        cur_hts = queue.pop()
        if cur_hts in seen:
            continue
        seen.add(cur_hts)
        for nb in adj.get(cur_hts, ()):
            if nb not in seen:
                queue.append(nb)

    focus = sorted(seed_hts)
    component = sorted(seen)

    # Edges to return: any edge touching the component (including references out to base).
    component_set = set(component)
    graph_edges = [
        e
        for e in edge_records
        if e["source"] in component_set
        or e["target"] in component_set
    ]
    # Prefer unique edges
    uniq = {(e["source"], e["target"], e["edge_type"]): e for e in graph_edges}
    # Always include the seed reference edges to this base line / ancestors
    for e in seed_edges:
        uniq[(e["source"], e["target"], e["edge_type"])] = e

    return {
        "focus": focus,
        "rules": [_serialize_rule(rules_by_hts[h]) for h in component if h in rules_by_hts],
        "edges": list(uniq.values()),
    }
